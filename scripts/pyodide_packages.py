#!/usr/bin/env python3


BUILD_DIR = "build"

import functools
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from typing import Any, Literal, Optional, TypedDict, Union, cast

import pkginfo
import requirements
from packaging.version import Version
from typing_extensions import NotRequired

top_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
package_source_dir = os.path.join(top_dir, "packages")
requirements_file = os.path.join(top_dir, "shinylive_requirements.json")
package_lock_file = os.path.join(top_dir, "shinylive_lock.json")

pyodide_dir = os.path.join(top_dir, "build", "shinylive", "pyodide")
packages_json_file = os.path.join(pyodide_dir, "packages.json")

usage_info = f"""
Find the versions of htmltools, shiny, and their dependencies that are needed to add to
the base Pyodide distribution.

Usage:
  pyodide_packages.py generate_lockfile
    Create/update shinylive_lock.json file, based on shinylive_requirements.json.

  pyodide_packages.py retrieve_packages
    Gets packages listed in lockfile, from local sources and from PyPI.
    Saves packages to {os.path.relpath(pyodide_dir)}.

  pyodide_packages.py update_pyodide_packages_json [pyodide_dir]
    Modifies pyodide's package.json to include Shiny-related packages.
    Modifies {os.path.relpath(packages_json_file)}
"""

# Packages that shouldn't be listed in "depends" in Pyodide's packages.json file.
AVOID_DEPEND_PACKAGES = [
    "typing",
    "python",
    # The next two are dependencies for Shiny, but they cause problems.
    # contextvars causes "NameError: name 'asyncio' is not defined". Not sure why. It's
    # already present anyway, as a built-in package.
    "contextvars",
    # websockets isn't used by Shiny when running in the browser.
    "websockets",
    # ipykernel is needed by ipywidgets. We've created a mock for it.
    "ipykernel",
    # This brings in IPython and a lot of unneeded dependencies with compiled code.
    "widgetsnbextension",
]


# =============================================
# Data structures used in our requirements.json
# =============================================
class RequirementsPackage(TypedDict):
    name: str
    source: Literal["local", "pypi"]
    version: Union[Literal["latest"], str]


# ====================================================
# Data structures used in our extra_packages_lock.json
# ====================================================
class LockfileDependency(TypedDict):
    name: str
    specs: list[tuple[str, str]]
    # version: Union[str, None]
    # operator: Union[Literal["~=", "==", "!=", ">=", "<=", ">", "<"], None]


class LockfilePackageInfo(TypedDict):
    name: str
    version: str
    filename: str
    sha256: Optional[str]
    url: Optional[str]
    depends: list[LockfileDependency]
    imports: list[str]


# =============================================
# Data structures returned by PyPI's JSON API
# =============================================
class PypiUrlInfo(TypedDict):
    comment_text: str
    digests: dict[str, str]
    downloads: int
    filename: str
    has_sig: bool
    md5_digest: str
    packagetype: Literal["source", "bdist_wheel"]
    python_version: Union[str, None]
    requires_python: Union[str, None]
    size: int
    upload_time: str
    upload_time_iso_8601: str
    url: str
    yanked: bool
    yanked_reason: Union[str, None]


# It's not clear exactly which of these fields can be None -- these are based on
# observations of a few packages, but might not be exactly right.
class PypiPackageInfo(TypedDict):
    author: str
    author_email: str
    bugtrack_url: Union[str, None]
    classifiers: list[str]
    description: str
    description_content_type: Union[str, None]
    docs_url: Union[str, None]
    download_url: str
    downloads: dict[str, int]
    home_page: str
    keywords: str
    license: str
    maintainer: Union[str, None]
    maintainer_email: Union[str, None]
    name: str
    package_url: str
    platform: str
    project_url: str
    project_urls: dict[str, str]
    release_url: str
    requires_dist: Union[list[str], None]
    requires_python: Union[str, None]
    summary: str
    version: str
    yanked: bool
    yanked_reason: Union[str, None]


class PypiPackageMetadata(TypedDict):
    info: PypiPackageInfo
    last_serial: int
    releases: dict[str, list[PypiUrlInfo]]
    urls: list[PypiUrlInfo]
    vulnerabilities: list[object]


# =============================================
# Data structures used in pyodide/packages.json
# =============================================
class PyodidePackageInfo(TypedDict):
    name: str
    version: str
    file_name: str
    install_dir: Literal["lib", "site"]
    depends: list[str]
    imports: list[str]
    unvendored_tests: NotRequired[bool]


# The package information structure used by Pyodide's packages.json.
class PyodidePackagesFile(TypedDict):
    info: dict[str, str]
    packages: dict[str, PyodidePackageInfo]


# =============================================================================
# Functions for generating the lockfile from the requirements file.
# =============================================================================
def generate_lockfile() -> None:
    print(
        f"Loading requirements package list from {os.path.relpath(requirements_file)}:"
    )
    with open(requirements_file) as f:
        required_packages: dict[str, RequirementsPackage] = json.load(f)

    print("  " + " ".join(required_packages.keys()))

    print("Finding dependencies...")
    required_package_info = _find_package_info_lockfile(required_packages)
    _recurse_dependencies_lockfile(required_package_info)
    print("All required packages and dependencies:")
    print("  " + " ".join(required_package_info.keys()))

    print(f"Writing {package_lock_file}")
    with open(package_lock_file, "w") as f:
        json.dump(required_package_info, f, indent=2, cls=MyEncoder)


def _recurse_dependencies_lockfile(
    pkgs: dict[str, LockfilePackageInfo],
) -> None:
    """
    Recursively find all dependencies of the given packages. This will mutate the object
    passed in.
    """
    pyodide_packages_info = orig_pyodide_packages()["packages"]
    i = 0
    while i < len(pkgs):
        pkg_info = pkgs[list(pkgs.keys())[i]]
        i += 1

        print(f"  {pkg_info['name']}:", end="")
        for dep in pkg_info["depends"]:
            dep_name = dep["name"]
            print(" " + dep_name, end="")
            if dep_name in pkgs or dep_name.lower() in pyodide_packages_info:
                # We already have it, either in our extra packages, or in the original
                # set of pyodide packages. Do nothing.
                # Note that the keys in pyodide_packages_info are all lower-cased, even
                # if the package name has capitals.
                pass
            else:
                pkgs[dep_name] = _find_package_info_lockfile_one(
                    {
                        "name": dep_name,
                        "source": "pypi",
                        # TODO: Use version from dependencies
                        "version": "latest",
                    }
                )
        print("")


def _find_package_info_lockfile(
    pkgs: dict[str, RequirementsPackage]
) -> dict[str, LockfilePackageInfo]:
    """
    Given a dict of RequirementsPackage objects, find package information that will be
    inserted into the package lock file. For PyPI packages, this involves fetching
    package metadata from PyPI.
    """
    res: dict[str, LockfilePackageInfo] = {}

    for pkg_name, pkg_info in pkgs.items():
        res[pkg_name] = _find_package_info_lockfile_one(pkg_info)
    return res


def _find_package_info_lockfile_one(
    pkg_info: RequirementsPackage,
) -> LockfilePackageInfo:
    """
    Given a RequirementsPackage object, find package information for it that will be
    inserted into the package lock file. For PyPI packages, this involves fetching
    package metadata from PyPI.
    """
    all_wheel_files = os.listdir(package_source_dir)
    all_wheel_files = [f for f in all_wheel_files if f.endswith(".whl")]

    if pkg_info["source"] == "local":
        wheel_file = [
            f for f in all_wheel_files if f.startswith(pkg_info["name"] + "-")
        ]
        if len(wheel_file) != 1:
            raise Exception(
                f"Expected exactly one wheel file for package {pkg_info['name']}, found {wheel_file}"
            )
        wheel_file = os.path.join(package_source_dir, wheel_file[0])
        return _get_local_wheel_info(wheel_file)

    elif pkg_info["source"] == "pypi":
        x = _get_pypi_package_info(pkg_info["name"], pkg_info["version"])
        return x

    else:
        raise Exception(f"Unknown source {pkg_info['source']}")


def _get_pypi_package_info(
    name: str, version: Union[Literal["latest"], str]
) -> LockfilePackageInfo:
    """
    Get the package info for a package from PyPI, and return it in our lockfile
    format.
    """

    (pkg_meta, wheel_url_info) = _find_pypi_meta_with_wheel(name, version)

    # Some packages have a different package name from the import (module) name.
    # "linkify-it-py" -> "linkify_it"
    # "python-multipart" -> "multipart"
    # There's no way to be certain of the import name from the package name, so it's
    # possible that in the future we'll need to special-case some packages.
    # https://stackoverflow.com/questions/11453866/given-the-name-of-a-python-package-what-is-the-name-of-the-module-to-import
    import_name = name.removeprefix("python-").removesuffix("-py").replace("-", "_")

    return {
        "name": name,
        "version": version,
        "filename": wheel_url_info["filename"],
        "sha256": wheel_url_info["digests"]["sha256"],
        "url": wheel_url_info["url"],
        "depends": _filter_requires(pkg_meta["info"]["requires_dist"]),
        "imports": [import_name],
    }


# Memoize this function because there may be many duplicate requests for the same
# package and version combination.
@functools.cache
def _find_pypi_meta_with_wheel(
    name: str, version: Union[Literal["latest"], str]
) -> tuple[PypiPackageMetadata, PypiUrlInfo]:
    """
    Find the URL information for the wheel file for a package from PyPI. Returns a tuple
    with version number and the PyPI URL information.
    """
    if version == "latest":
        version = ""
    else:
        version = "/" + version

    pkg_meta: PypiPackageMetadata
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}{version}/json") as f:
            pkg_meta = cast(PypiPackageMetadata, json.load(f))
    except urllib.error.HTTPError as e:
        raise Exception(f"Error getting package info for {name} from PyPI: {e}")

    def url_info_is_wheel(x: PypiUrlInfo) -> bool:
        return x["packagetype"] == "bdist_wheel" and x["filename"].endswith(
            "py3-none-any.whl"
        )

    for url_info in pkg_meta["urls"]:
        if url_info_is_wheel(url_info):
            return (pkg_meta, url_info)

    # If we made it here, then we didn't find a wheel in the "urls" section. Iterate
    # backwards through the releases, and find the most recent one that has a wheel.
    all_versions = pkg_meta["releases"].keys()
    all_versions = sorted(all_versions, key=lambda v: Version(v), reverse=True)

    for v in all_versions:
        url_infos: list[PypiUrlInfo] = pkg_meta["releases"][v]
        for url_info in url_infos:
            if url_info_is_wheel(url_info):
                # Now that we've found the version with a wheel, call this function
                # again, but ask for that specific version.
                return _find_pypi_meta_with_wheel(name, v)

    raise Exception(f"No wheel URL found for {name} from PyPI")


def _get_local_wheel_info(file: str) -> LockfilePackageInfo:
    """
    Get package info from a local wheel file.
    """
    info: Any = pkginfo.Wheel(file)  # type: ignore
    res: LockfilePackageInfo = {
        "name": info.name,
        "version": info.version,
        "filename": os.path.basename(file),
        "sha256": None,
        "url": None,
        "depends": _filter_requires(info.requires_dist),
        "imports": [info.name],
    }
    # Note that it is possible for the imports field to differ from the package name
    # (and it is nontrivial to find the actual modules provided by a package). But for
    # the packages we're using from local wheels, that is not the case. If this changes
    # in the future, we can find a better.

    return res


# Given input like this:
# [
#   "mdurl~=0.1",
#   "h11 (>=0.8)",
#   "foo",
#   "typing_extensions>=3.7.4;python_version<'3.8'",
#   "psutil ; extra == \"benchmarking\"",
#   "coverage ; extra == \"testing\"",
#   "pytest ; extra == \"testing\"",
# ]
#
# Return this:
# ["mdurl", "h11", "foo"]
#
# It's a little dumb in that it ignores python_version, but it's sufficient for our use.
def _filter_requires(requires: Union[list[str], None]) -> list[LockfileDependency]:
    if requires is None:
        return []

    def _get_dep_info(dep_str: str) -> LockfileDependency:
        reqs = requirements.parse(dep_str)
        req = next(reqs)
        if next(reqs, None) is not None:
            raise Exception(f"More than one requirement in {dep_str}")
        return {
            "name": req.name,
            "specs": req.specs,  # type: ignore - Due to a type bug in requirements package.
        }

    # Remove package descriptions with extras, like "scikit-learn ; extra == 'all'"
    res = filter(lambda x: ";" not in x, requires)
    # Strip off version numbers: "python-dateutil (>=2.8.2)" => "python-dateutil"
    res = map(_get_dep_info, res)
    # Filter out packages that cause problems.
    res = filter(lambda x: x["name"] not in AVOID_DEPEND_PACKAGES, res)
    res = map(NoIndent, res)
    return list(res)


# =============================================================================
# Functions for copying and downloading the wheel files.
# =============================================================================
def retrieve_packages():
    """
    Download packages listed in the lockfile, either from PyPI, or from local wheels, as
    specified in the lockfile.
    """
    with open(package_lock_file, "r") as f:
        packages: dict[str, LockfilePackageInfo] = json.load(f)

    print(f"Copying packages to {os.path.relpath(pyodide_dir)}")

    for pkg_info in packages.values():
        destfile = os.path.join(pyodide_dir, pkg_info["filename"])

        if pkg_info["url"] is None:
            srcfile = os.path.join(package_source_dir, pkg_info["filename"])
            print("  Copying " + os.path.relpath(srcfile))
            shutil.copyfile(srcfile, destfile)
        else:
            if os.path.exists(destfile):
                print(f"  {destfile} already exists. Checking SHA256... ", end="")
                if _sha256_file(destfile) == pkg_info["sha256"]:
                    print("OK")
                    continue
                else:
                    print("Mismatch! Downloading...")

            print("  " + pkg_info["url"])
            req = urllib.request.urlopen(pkg_info["url"])
            with open(destfile, "b+w") as f:
                f.write(req.read())

        if pkg_info["sha256"] is not None:
            sha256 = _sha256_file(destfile)
            if sha256 != pkg_info["sha256"]:
                raise Exception(
                    f"SHA256 mismatch for {pkg_info['url']}.\n"
                    + f"  Expected {pkg_info['sha256']}\n"
                    + f"  Actual   {sha256}"
                )


def _sha256_file(filename: str) -> str:
    with open(filename, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# =============================================================================
# Functions for modifying the pyodide/packages.json file with the extra packages.
# =============================================================================
def update_pyodide_packages_json():
    pyodide_packages = orig_pyodide_packages()

    print(
        f"Adding package information from {package_lock_file} into {packages_json_file}"
    )

    with open(package_lock_file, "r") as f:
        lockfile_packages = cast(dict[str, LockfilePackageInfo], json.load(f))

    print("Adding packages to Pyodide packages:")
    for name, pkg_info in lockfile_packages.items():
        if name in pyodide_packages:
            raise Exception(f"  {name} already in {packages_json_file}")

        print(f"  {name}")
        pyodide_packages["packages"][name] = _lockfile_to_pyodide_package_info(pkg_info)

    print("Writing pyodide/packages.json")
    with open(packages_json_file, "w") as f:
        json.dump(pyodide_packages, f)


def _lockfile_to_pyodide_package_info(pkg: LockfilePackageInfo) -> PyodidePackageInfo:
    """
    Given the information about a package from the lockfile, translate it to the format
    used by pyodide/packages.json.
    """
    return {
        "name": pkg["name"],
        "version": pkg["version"],
        "file_name": pkg["filename"],
        "install_dir": "site",
        "depends": [x["name"] for x in pkg["depends"]],
        "imports": pkg["imports"],
    }


def orig_pyodide_packages() -> PyodidePackagesFile:
    """
    Read in the original Pyodide packages.json from the Pyodide directory. If it doesn't
    already exist, this will make a copy, named packages.orig.json. Then it will read in
    packages.orig.json and return the "packages" field.
    """

    orig_packages_json_file = os.path.join(
        os.path.dirname(packages_json_file), "packages.orig.json"
    )

    if not os.path.isfile(orig_packages_json_file):
        print(
            f"{os.path.relpath(orig_packages_json_file)} does not exist. "
            + f" Copying {os.path.relpath(packages_json_file)} to {os.path.relpath(orig_packages_json_file)}."
        )
        shutil.copy(packages_json_file, orig_packages_json_file)

    with open(orig_packages_json_file, "r") as f:
        pyodide_packages_info = cast(PyodidePackagesFile, json.load(f))

    return pyodide_packages_info


# =============================================================================
# JSON encoder
# =============================================================================
class NoIndent(object):
    """Value wrapper."""

    def __init__(self, value: object):
        # if not isinstance(value, (list, tuple)):
        #     raise TypeError("Only lists and tuples can be wrapped")
        self.value = value

    def __getitem__(self, index: object) -> Any:
        return self.value[index]


from _ctypes import PyObj_FromPtr  # see https://stackoverflow.com/a/15012814/355230


class MyEncoder(json.JSONEncoder):
    FORMAT_SPEC = "@@{}@@"  # Unique string pattern of NoIndent object ids.
    regex = re.compile(FORMAT_SPEC.format(r"(\d+)"))  # compile(r'@@(\d+)@@')

    def __init__(self, **kwargs: object):
        # Keyword arguments to ignore when encoding NoIndent wrapped values.
        ignore = {"cls", "indent"}

        # Save copy of any keyword argument values needed for use here.
        self._kwargs = {k: v for k, v in kwargs.items() if k not in ignore}
        super(MyEncoder, self).__init__(**kwargs)

    def default(self, o: object):
        if isinstance(o, NoIndent):
            return self.FORMAT_SPEC.format(id(o))
        else:
            return super(MyEncoder, self).default(o)

    def iterencode(self, o: object, **kwargs: object):
        format_spec = self.FORMAT_SPEC  # Local var to expedite access.

        # Replace any marked-up NoIndent wrapped values in the JSON repr
        # with the json.dumps() of the corresponding wrapped Python object.
        for encoded in super(MyEncoder, self).iterencode(o, **kwargs):
            match = self.regex.search(encoded)
            if match:
                id = int(match.group(1))
                no_indent = PyObj_FromPtr(id)
                json_repr = json.dumps(no_indent.value, **self._kwargs)
                # Replace the matched id string with json formatted representation
                # of the corresponding Python object.
                encoded = encoded.replace(
                    '"{}"'.format(format_spec.format(id)), json_repr
                )

            yield encoded


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print(usage_info)
        sys.exit(1)

    if sys.argv[1] == "generate_lockfile":
        generate_lockfile()

    elif sys.argv[1] == "retrieve_packages":
        retrieve_packages()

    elif sys.argv[1] == "update_pyodide_packages_json":
        update_pyodide_packages_json()

    else:
        print(usage_info)
        sys.exit(1)