| track | model | config | runs | exposure | ASR dedup / exposed [95 % CI] | raw ASR | utility (no attack) | utility (attack) | no output | overflow |
|---|---|---|---|---|---|---|---|---|---|---|
| mcp/mcp_result | gpt-4o-mini | EN/EN | 153 | 142/153 (93%) | 10/142 (7%) [4%, 12%] | 10/153 (7%) | 12/24 (50%) | 62/153 (41%) | 0 | 0 |
| mcp/tp_third_party | gpt-4o-mini | EN/EN | 153 | 153/153 (100%) | 4/153 (3%) [1%, 7%] | 4/153 (3%) | 12/24 (50%) | 71/153 (46%) | 0 | 0 |
| mcp/tp_trusted | gpt-4o-mini | EN/EN | 153 | 153/153 (100%) | 6/153 (4%) [2%, 8%] | 6/153 (4%) | 12/24 (50%) | 72/153 (47%) | 0 | 0 |

Control (injection task given as the user task):
- mcp / gpt-4o-mini / mcp_shop: 7/8 solved

| track | model | comparison | exposed pairs | only A / only B | ASR A - B [95 % CI] | p | p (Holm) |
|---|---|---|---|---|---|---|---|

MCP vectors (notes/protocol.md 3.5, H5)

| model | config | comparison | exposed pairs | only A / only B | ASR A - B [95 % CI] | p | p (Holm) |
|---|---|---|---|---|---|---|---|
| gpt-4o-mini | EN/EN | tp_third_party vs mcp_result | 142 | 0 / 6 | -4.2% [-7.3%, -1.4%] | 0.0312 | 0.0938 |
| gpt-4o-mini | EN/EN | tp_third_party vs tp_trusted | 153 | 2 / 4 | -1.3% [-4.5%, +1.3%] | 0.688 | 0.688 |
| gpt-4o-mini | EN/EN | mcp_result vs tp_trusted | 142 | 6 / 2 | +2.8% [+0.0%, +6.0%] | 0.289 | 0.578 |
