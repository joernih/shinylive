import { AppEngine } from "./App";
import { FCtoFCJSON, FileContent } from "./filecontent";
import LZString from "lz-string";

const shortEngine = {
  python: "py",
  r: "r",
}
export function editorUrlPrefix(engine: AppEngine) {
  return `https://shinylive.io/${shortEngine[engine]}/editor/`;
}

export function appUrlPrefix(engine: AppEngine) {
  return `https://shinylive.io/${shortEngine[engine]}/app/`;
}

/**
 * Given a FileContent[] object, return a string that is a LZ-compressed JSON
 * representation of it.
 */
export function fileContentsToUrlString(
  fileContents: FileContent[],
  sort: boolean = true
): string {
  if (sort) {
    fileContents.sort((a, b) => a.name.localeCompare(b.name));
  }
  return LZString.compressToEncodedURIComponent(
    JSON.stringify(fileContents.map(FCtoFCJSON))
  );
}
