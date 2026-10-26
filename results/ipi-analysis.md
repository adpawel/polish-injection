| track | model | config | runs | exposure | ASR dedup / exposed [95 % CI] | raw ASR | utility (no attack) | utility (attack) | no output | overflow |
|---|---|---|---|---|---|---|---|---|---|---|
| ipi | gpt-4o-mini | EN/EN | 400 | 380/400 (95%) | 107/380 (28%) [24%, 33%] | 107/400 (27%) | 20/24 (83%) | 84/240 (35%) | 5 | 0 |
| ipi | gpt-4o-mini | EN/PL | 400 | 380/400 (95%) | 63/380 (17%) [13%, 21%] | 63/400 (16%) | 20/24 (83%) | 128/240 (53%) | 3 | 0 |
| ipi | gpt-4o-mini | PL/EN | 400 | 390/400 (98%) | 105/390 (27%) [23%, 32%] | 105/400 (26%) | 18/24 (75%) | 89/240 (37%) | 4 | 0 |
| ipi | gpt-4o-mini | PL/PL | 400 | 387/400 (97%) | 97/387 (25%) [21%, 30%] | 97/400 (24%) | 18/24 (75%) | 89/240 (37%) | 3 | 0 |

Control (injection task given as the user task):
- ipi / gpt-4o-mini: 7/10 solved

| track | model | comparison | exposed pairs | only A / only B | ASR A - B [95 % CI] | p | p (Holm) |
|---|---|---|---|---|---|---|---|
| ipi | gpt-4o-mini | EN/EN vs EN/PL | 380 | 57 / 13 | +11.6% [+7.1%, +16.1%] | 1.03e-07 | 5.14e-07 |
| ipi | gpt-4o-mini | EN/EN vs PL/EN | 379 | 24 / 21 | +0.8% [-3.2%, +5.3%] | 0.766 | 0.766 |
| ipi | gpt-4o-mini | EN/EN vs PL/PL (primary) | 377 | 37 / 25 | +3.2% [-1.9%, +8.6%] | 0.162 | - |
| ipi | gpt-4o-mini | EN/PL vs PL/EN | 379 | 15 / 56 | -10.8% [-16.4%, -5.5%] | 1.04e-06 | 4.17e-06 |
| ipi | gpt-4o-mini | EN/PL vs PL/PL | 377 | 14 / 46 | -8.5% [-13.5%, -3.2%] | 4.22e-05 | 0.000127 |
| ipi | gpt-4o-mini | PL/EN vs PL/PL | 386 | 34 / 26 | +2.1% [-2.8%, +7.1%] | 0.366 | 0.733 |
