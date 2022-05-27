import { Extension } from "@codemirror/state";
import * as React from "react";
import {
  EditorFile,
  editorFileToFileContent,
  fileContentsToEditorFiles,
  fileContentToEditorFile,
} from "../Editor";
import type { FileContent } from "../filecontent";

export function useTabbedCodeMirror({
  currentFilesFromApp,
  inferEditorExtensions,
}: {
  currentFilesFromApp: FileContent[];
  inferEditorExtensions: (f: FileContent) => Extension;
}) {
  const [files, setFiles] = React.useState<EditorFile[]>([]);

  // A counter that increments each time a new file is added by clicking the plus
  // button. It is reset when a new set of files is received from the parent.
  const [newFileCounter, setNewFileCounter] = React.useState(1);

  const [activeFileIdx, setActiveFileIdx] = React.useState(0);

  // If a file name is being edited, this will be an object with index and name
  // (as it is being edited); otherwise it's null when no renaming is happening.
  const [editingFilename, setEditingFilename] = React.useState<string | null>(
    null
  );

  // ===========================================================================
  // Callback to run each time we receive a new set of files from the parent
  // App.
  // ===========================================================================
  React.useEffect(() => {
    setFiles(
      fileContentsToEditorFiles(currentFilesFromApp, inferEditorExtensions)
    );
    setActiveFileIdx(0);

    setNewFileCounter(1);
  }, [currentFilesFromApp, inferEditorExtensions]);

  // ===========================================================================
  // File adding/removing/renaming
  // ===========================================================================
  function closeFile(e: React.SyntheticEvent, index: number) {
    e.stopPropagation();

    const updatedFiles = [...files];
    updatedFiles.splice(index, 1);
    setFiles(updatedFiles);

    if (activeFileIdx > updatedFiles.length - 1) {
      // If we were on the last (right-most) tab and it was closed, set the
      // active tab to the new right-most tab.
      setActiveFileIdx(updatedFiles.length - 1);
    }
  }

  function addFile() {
    const newFile: EditorFile = fileContentToEditorFile(
      {
        name: `file${newFileCounter}.py`,
        type: "text",
        content: `def add(x, y):\n  return x + y\n`,
      },
      inferEditorExtensions
    );

    setEditingFilename(newFile.name);
    setNewFileCounter(newFileCounter + 1);
    setFiles([...files, newFile]);
    setActiveFileIdx(files.length);
  }

  function renameFile(oldFileName: string, newFileName: string) {
    const updatedFiles = [...files];
    const fileIndex = updatedFiles.findIndex((f) => f.name === oldFileName);

    updatedFiles[fileIndex].name = newFileName;

    // This is a little inefficient, but it does the job: convert to FileContent
    // so that we can infer the new editor extensions (which can depend on file
    // type), and then convert back to EditorFile, and save it back in the
    // original slot.
    updatedFiles[fileIndex] = fileContentToEditorFile(
      editorFileToFileContent(updatedFiles[fileIndex]),
      inferEditorExtensions
    );
    setFiles(updatedFiles);

    setEditingFilename(null);
    setActiveFileIdx(fileIndex);
  }

  function selectFile(fileName: string) {
    const fileIndex = files.findIndex((f) => f.name === fileName);

    if (activeFileIdx === fileIndex) {
      // User has clicked on the currently selected file tab, so turn on rename
      // mode.
      setEditingFilename(fileName);
    } else {
      // Otherwise this is just a normal file switch.
      setActiveFileIdx(fileIndex);
    }
  }

  function enterNameEditMode(name: string | null) {
    if (name === null) {
      setEditingFilename(null);
      return;
    }
    setEditingFilename(name);
  }

  const activeFile = files[activeFileIdx];

  return {
    files,
    activeFile,
    editingFilename,
    addFile,
    renameFile,
    closeFile,
    selectFile,
    enterNameEditMode,
  };
}