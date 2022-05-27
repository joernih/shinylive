import * as React from "react";
import { ToHtmlResult } from "../pyodide-proxy";
import { PyodideProxyHandle } from "../hooks/usePyodide";
import { TerminalMethods } from "./Terminal";
import "./OutputCell.css";

// =============================================================================
// OutputCell component
// =============================================================================
export function OutputCell({
  pyodideProxyHandle,
  setTerminalMethods,
}: {
  pyodideProxyHandle: PyodideProxyHandle;
  setTerminalMethods: React.Dispatch<React.SetStateAction<TerminalMethods>>;
}) {
  const [content, setContent] = React.useState<ToHtmlResult>({
    type: "text",
    value: "",
  });

  React.useEffect(() => {
    const runCodeInTerminal = async (command: string): Promise<void> => {
      if (!pyodideProxyHandle.ready) return;

      try {
        const result = await pyodideProxyHandle.pyodide.runPyAsync(command, {
          returnResult: "to_html",
          printResult: false,
        });

        setContent(result);
      } catch (e) {
        setContent({ type: "text", value: (e as Error).message });
      }
    };

    setTerminalMethods({
      ready: true,
      runCodeInTerminal,
    });
  }, [setTerminalMethods, pyodideProxyHandle]);

  return (
    <div className="OutputCell">
      {content.type === "html" ? (
        <div
          className="rendered_html"
          dangerouslySetInnerHTML={{ __html: content.value }}
        ></div>
      ) : (
        <pre className="sourceCode">
          <code className="sourceCode">{content.value}</code>
        </pre>
      )}
    </div>
  );
}