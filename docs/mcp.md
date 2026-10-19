# 用 MCP 接入 / Connecting over MCP

brainlib 可以作为 MCP 服务器运行，给 Claude Desktop 这类不能直接运行命令、但支持 MCP 的应用使用。
工具和命令行一一对应，拒绝规则完全相同。需要用户本人终端的操作（设置和打开保险箱、终端里逐条审批）不通过 MCP 提供。

brainlib runs as an MCP server for apps that support MCP. Tools mirror the CLI with the
same refusals. Anything that needs the owner's own terminal (vault setup and opening,
interactive review) is deliberately not offered over MCP.

## 配置 / Configuration

在应用的 MCP 配置里加一项（路径换成这台电脑上的实际路径）：

Add a server entry to the app's MCP config (use real paths on this computer):

macOS / Linux:

```json
{
  "mcpServers": {
    "brainlib": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/brainlib/brainlib.py", "mcp", "--library", "/ABSOLUTE/PATH/TO/YOUR/LIBRARY"]
    }
  }
}
```

Windows:

```json
{
  "mcpServers": {
    "brainlib": {
      "command": "py",
      "args": ["-3", "C:\\ABSOLUTE\\PATH\\TO\\brainlib\\brainlib.py", "mcp", "--library", "C:\\ABSOLUTE\\PATH\\TO\\YOUR\\LIBRARY"],
      "env": {"PYTHONUTF8": "1"}
    }
  }
}
```

## 工具 / Tools

| Tool | Same as |
|---|---|
| kb_next | `brainlib next` |
| kb_agent_check | `brainlib agent-check` |
| kb_lang | `brainlib lang` |
| kb_doctor | `brainlib doctor` |
| kb_find / kb_read / kb_index / kb_health | `find` / `read` / `index` / `health` |
| kb_note | `brainlib note` (`provenance`: said, judgment, extracted, inferred, guess, external; `private`: true or false, needed once the user has marked sensitive topics; `now` with `target`: make the suggested change right away) |
| kb_onboard | `brainlib onboard` |
| kb_classify | `brainlib classify` |
| kb_proposals | `brainlib review` |
| kb_decide | `apply` / `reject` / `defer`; apply and reject need `user_confirmed: true` and the user's words |
