// =======================================================================
// Utility functions
// =======================================================================
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function makeRandomKey(length = 5): string {
  let result = "";
  const characters = "abcdefghijklmnopqrstuvwxyz0123456789";
  const charactersLength = characters.length;
  for (let i = 0; i < length; i++) {
    result += characters.charAt(Math.floor(Math.random() * charactersLength));
  }
  return result;
}

// Given a path, return the path with the last element removed. Note that
// result will not have a trailing slash.
// For example:
// "/ab/cd"  -> "/ab"
// "/ab/cd/" -> "/ab"
// "/ab/"    -> ""
// "ab/cd"   -> "ab"
// "ab/"     -> ""
// "ab"      -> ""
// "/"       -> Error
// ""        -> Error
export function dirname(path: string) {
  if (path === "/" || path === "") {
    throw new Error("Cannot get dirname() of root directory.");
  }
  return path.replace(/[/]?[^/]+[/]?$/, "");
}

export function basename(path: string) {
  return path.replace(/.*\//, "");
}

// Get the path to the current script, when used in a JS module. Note: for
// non-modules, something similar could be done by combining window.location.pathname
// and document.currentScript.
export function currentScriptPath(): string {
  return new URL(import.meta.url).pathname;
}

// Get the directory containing the current script, when used in a JS module.
export function currentScriptDir(): string {
  return dirname(currentScriptPath());
}

export function loudPrint(msg: string) {
  console.log("%c" + msg, "color:forestgreen");
}

// Given a filename, return the file type.
export function inferFiletype(filename: string): string | null {
  const extMatch = filename.match(/\.[0-9a-z]+$/i);
  if (extMatch === null) {
    return null;
  }

  // Get matched string and remove leading '.'
  const ext = extMatch[0].substring(1).toLowerCase();
  const type = FILE_EXTENSIONS[ext];
  if (!type) {
    return null;
  }

  return type;
}

const FILE_EXTENSIONS: Record<string, string> = {
  py: "python",
  js: "javascript",
  html: "html",
  css: "css",
  csv: "csv",
  r: "r",
};

export function isApplePlatform(): boolean {
  return /(Mac|iPhone|iPod|iPad)/i.test(navigator.userAgent);
}

export function modKeySymbol(): string {
  if (isApplePlatform()) {
    return "⌘";
  } else {
    return "Ctrl";
  }
}

// Use a heuristic to guess if an ArrayBuffer contains binary data, as opposed
// to text.
export function isBinary(buf: ArrayBuffer): boolean {
  const numBytes = Math.min(buf.byteLength, 1024);
  const bytes = new Uint8Array(buf, 0, numBytes);
  for (const b of bytes) {
    if (b === 0 || b === 255) {
      return true;
    }
  }
  return false;
}

export function arrayBufferToBinaryString(buf: ArrayBuffer): string {
  const byteArray = new Uint8Array(buf);
  let result = "";
  for (let i = 0; i < byteArray.length; i++) {
    result += String.fromCharCode(byteArray[i]);
  }
  return result;
}

export function binaryStringtoUint8Array(s: string): Uint8Array {
  const len = s.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = s.charCodeAt(i);
  }
  return bytes;
}