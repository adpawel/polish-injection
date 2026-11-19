| track | model | config | runs | exposure | ASR dedup / exposed [95 % CI] | raw ASR | utility (no attack) | utility (attack) | no output | overflow |
|---|---|---|---|---|---|---|---|---|---|---|
| mcp/mcp_result | gpt-4o-mini | EN/EN | 192 | 181/192 (94%) | 112/181 (62%) [55%, 69%] | 112/192 (58%) | 10/24 (42%) | 89/192 (46%) | 1 | 0 |
| mcp/tp_third_party | gpt-4o-mini | EN/EN | 192 | 192/192 (100%) | 0/192 (0%) [0%, 2%] | 0/192 (0%) | 10/24 (42%) | 85/192 (44%) | 0 | 0 |
| mcp/tp_trusted | gpt-4o-mini | EN/EN | 192 | 192/192 (100%) | 0/192 (0%) [0%, 2%] | 0/192 (0%) | 10/24 (42%) | 93/192 (48%) | 1 | 0 |

Control (injection task given as the user task):
- mcp / gpt-4o-mini / mcp_shop: 8/8 solved

| track | model | comparison | exposed pairs | only A / only B | ASR A - B [95 % CI] | p | p (Holm) |
|---|---|---|---|---|---|---|---|

MCP vectors (notes/protocol.md 3.5, H5)

| model | config | comparison | exposed pairs | only A / only B | ASR A - B [95 % CI] | p | p (Holm) |
|---|---|---|---|---|---|---|---|
| gpt-4o-mini | EN/EN | tp_third_party vs mcp_result | 181 | 0 / 112 | -61.9% [-68.5%, -54.7%] | 3.85e-34 | 7.7e-34 |
| gpt-4o-mini | EN/EN | tp_third_party vs tp_trusted | 192 | 0 / 0 | +0.0% [+0.0%, +0.0%] | n/a | n/a |
| gpt-4o-mini | EN/EN | mcp_result vs tp_trusted | 181 | 112 / 0 | +61.9% [+54.7%, +68.5%] | 3.85e-34 | 7.7e-34 |
