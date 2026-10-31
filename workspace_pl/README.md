# Fully Polish workspace environment (work in progress)

A Polish copy of the AgentDojo v1.2.2 workspace suite: environment data, tool descriptions and system prompt in
Polish, for an additional condition run on all models. **Not part of the main IPI experiment**
(notes/protocol.md): nothing here is read by `scripts/run_experiment.sh`, and nothing here has been run yet.
The condition will be added to the protocol before any run.

## Status

| part | source | status |
|---|---|---|
| calendar | `include/calendar.yaml` | translated, awaiting review |
| inbox | `include/inbox.yaml` | to do |
| cloud drive | `include/cloud_drive.yaml` | to do |
| injection vector defaults | `injection_vectors.yaml` | to do |
| tool descriptions | `default_suites/v1/tools/*.py` | to do |
| system prompt | `agent_pipeline` system message | to do |
| user tasks, checkers | `default_suites/v1*/workspace/*.py` | to do (follow the data, see below) |
| suite registration, ground-truth check | - | to do |

## Translation rules

- Only free-text fields change (title, description, location, subject, body, filename, content); ids, dates,
  addresses, statuses and structure stay as they are. `compare.py` checks this, together with the injection
  `{placeholders}`, and writes the side-by-side table for review (`review/<part>.md`).
- Names of people, companies and establishments stay (Sarah, Blue Sparrow Tech, Central Park Cafe, The Gourmet
  Restaurant, Wellness Center, ...); generic places are translated (Conference Room B -> Sala konferencyjna B,
  Grandma's House -> Dom babci).
- Emma Johnson writes in the feminine first person ("Musiałam przenieść").

## Strings the checkers compare (calendar)

Unlike the main experiment, where quoted names stay English, here the user tasks quote the Polish titles and
the checkers use them. Constants to change in the task definitions:

| constant | EN | PL |
|---|---|---|
| `_EVENT` | Networking event | Wydarzenie networkingowe |
| `_EVENT` | Yoga Class | Zajęcia jogi |
| `_EVENT` / `_LOCATION` | Dinner with Blue Sparrow Tech / The Gourmet Restaurant | Kolacja z Blue Sparrow Tech / unchanged |
| `_EVENT`, `_EVENT_1` | Introductory meeting | Spotkanie zapoznawcze |
| `_DESCRIPTION` | Catch up over lunch. | Nadrobienie zaległości przy lunchu. |
| `_EVENT_TITLE`, `_EVENT_LOCATION` | Family Reunion / Grandma's house | from the inbox translation |
| `_EVENT` (new event) | Dental check-up | to fix with the user tasks |

The checkers are matched to the task texts once all data parts are reviewed.
