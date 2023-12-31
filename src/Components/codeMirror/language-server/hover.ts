import {
  createUri,
  LanguageServerClient,
} from "../../../language-server/client";
import { LSPClient } from "../../../language-server/lsp-client";
import { renderDocumentation } from "./documentation";
import { offsetToPosition } from "./positions";
import { Extension } from "@codemirror/state";
import { hoverTooltip, Tooltip } from "@codemirror/view";
import {
  HoverParams,
  HoverRequest,
  MarkupContent,
} from "vscode-languageserver-protocol";

export function hover(lspClient: LSPClient, filename: string): Extension {
  return createHoverTooltip(lspClient.client, filename);
}

function createHoverTooltip(
  client: LanguageServerClient,
  filename: string
): Extension {
  const uri = createUri(filename);

  return hoverTooltip(async (view, pos, side): Promise<Tooltip | null> => {
    offsetToPosition(view.state.doc, pos);

    const params: HoverParams = {
      textDocument: { uri },
      position: offsetToPosition(view.state.doc, pos),
    };

    const result = await client.connection.sendRequest(
      HoverRequest.type,
      params
    );
    if (result === null) return null;

    // console.log(result);

    return {
      pos: pos,
      above: true,
      create(view) {
        const dom = renderDocumentation(result?.contents as MarkupContent);
        // console.log(dom);
        return { dom };
      },
    };
  });
}
