# RBVM Agent

Risk-Based Vulnerability Management (RBVM) agent uses Claude, a set of `[VM]` (Vulnerability Management) skills, and connected MCP servers to automate the vulnerability management lifecycle. It collects prioritized findings from Tenable, groups them into actionable cards/tickets per team, saves them in a local database, opens and closes Azure DevOps work items (cards/tickets), and reports progress on a dashboard.

---

## Workflow

<img width="805" height="150" alt="image" src="https://github.com/user-attachments/assets/d3ec3c7b-662d-4332-a970-4ff5cc91e26d" />


| Step | Skill | Input | Output |
|------|-------|-------|--------|
| 1 | `vm-policy-based-vulnerability-grouping` | Tenable VM (via HexaAI) + `PolicyGV.txt`, `Severity.txt`, `SLA.txt`, `Mitigations.txt` | Markdown file with grouped vulnerabilities (one row = one future card) |
| 2 | `vm-save-data-on-sqlite3-database` | Output of step 1 | Records in `agent_output.db`, one table per query |
| 3 | `vm-azuredevops-vulnerability-orchestrator` | `agent_output.db` + `AreaPath.txt` + `SLA.txt` | Azure DevOps *Vulnerability* work items (cards/tickets), with the DB updated (AzureID, status, dates) |
| 4 | `vm-vulnerability-analytics-dashboard` | Azure DevOps Analytics (OData) + `agent_output.db` | Downloadable HTML dashboard |

> The skill names in this table are the folder names. The names Claude shows come from the `name:` field of each `SKILL.md` (see Setup, step 2).

The cycle runs again on every new request. Steps 2 and 3 compare each new requests with what is already stored, so the agent does not create duplicate cards and closes cards whose findings have been fixed.

*Local Azure MCP Server

> **Usage Recommendation —** This agent should be scheduled to run following the completion of scans across your company’s critical environments, ensuring that it can perform the necessary actions immediately after the latest results have been collected from scans.

---

## What it does

### `[VM] Policy-Based Vulnerability Grouping (Skill)`

Acts as a member of the Vulnerability Management team:

- Uses **HexaAI** inside the Tenable Vulnerability Management console to list the most important vulnerabilities, based on the queries defined in the Vulnerability Management company Standard (`PolicyGV.txt`).
- **Groups** findings that belong in the same card. Grouping rules:
  - ✅ Same vulnerability or remediation (e.g. OS patching, Oracle CPU for WebLogic) on several assets that share the same `CORE_TEAM` tag → **one card**.
  - ❌ Different vulnerabilities, even if they have the same team → separate cards.
  - ❌ Same vulnerability on assets with different `CORE_TEAM` teams → separate cards.
- Produces a table with these fields: `ID | Finding IDs | Title | Description | Assets | Evidence | Responsible Team | Solution | Mitigation | References | Severity | Remediation Deadline | Source Query | Pending Items`.
- `Pending Items` keeps only the finding IDs that are still open, so it shrinks as teams remediate.
- `Mitigation` based on company's mitigations/detectives technology (Mitigation.txt) the agent suggests possible workarounds/compensating controls to minimize risks levels.

> This skill works not only with Vulnerability Management module but also Web Application Scanning, it all depends on your query.

### `[VM] Save-data-on-sqlite3-database (Skill)`

Saves the grouped output in the SQLite database through the sqlite3 MCP:

- One table per policy query: `query1` … `query7`.
- **First run:** inserts all rows. `AzureID`, `Alert30/15/5`, `CreatedDate`, `ClosedDate` and `StatusCardAzure` start as `NULL`.
- **Later runs:** compares the new HexaAI output with the table of the same query, matching on `FindingID`. It does **not** create a new record when the finding already belongs to a record whose card is not Closed. It inserts records only for groupings that are new.

### `[VM] AzureDevops Vulnerability Orchestrator (Skill)`

Syncs the database with Azure DevOps through the `local AzureDevops` MCP:

- **Records without an AzureID:** creates a *Vulnerability* work item (card/ticket), maps the fields, then writes `AzureID`, `CreatedDate`, `UpdatedAt` and `StatusCardAzure` back to the DB.
- **Records with an AzureID:** applies the decision tree in `status-change-criteria.md`:
  - Card is **Closed/Canceled** → open a new card and update `StatusCardAzure`.
  - Card is **Resolved** and the evidence is the same:
    - Findings still pending → reactivate the card (`Active`) and add a comment listing the paths that are still vulnerable.
    - No findings pending → close the card and set `ClosedDate`, `UpdatedAt` and `StatusCardAzure = Closed`.
  - Card is **Resolved** and the evidence is different:
    - All old evidence is fixed but new evidence is pending → open a new card with the new evidence only, then close the old card.
    - Extra evidence was found → open a new card with the extra evidence only.
- Follows strict card formatting rules:
  - Do not abbreviate anything.
  - Do not guess the application from the server name.
  - Do not put the server name in the Title.
  - Base the Description on the plugin with the highest CVSSv3, and give Impact its own section.
  - Put one finding per line in Evidence and one action per line in Solution.
  - Put plugin IDs and finding IDs in a section labelled *"Information for the VM team"*.
  - Leave 2 blank lines between sections.
  - Keep Severity, DueDate and DetectionOrigin out of the Description (they have their own fields).

### `[VM] Vulnerability Analytics Dashboard (Skill)`

Builds an HTML dashboard (light theme, last-updated timestamp) from Azure DevOps Analytics (OData), joined with `agent_output.db` (`WorkItemId` ↔ `AzureID`). The dashboard must never show made-up data. If the `local Azure MCP` connection fails, it does not build the visuals. Contents:

- **Trend charts**, all with Year → Month → Day drill-down:
  - Cumulative Pending vs. Fixed.
  - Cumulative Pending by severity.
  - New vs. Fixed by CreatedDate.
- **KPI cards:**
  - Total Reported, Emergency, Critical + High, Deadline Extension and Awaiting Validation (Resolved).
  - Each card shows % Closed, % Overdue and a 30-day trend line.
- **Pyramid:** pending cards for Query 1 (top), Query 2 and Query 3 (base).
- **Breakdowns:**
  - Pending by Tribe, split by query, with Tribe → Manager drill-down.
  - By Severity, by Brand (`V_ImpactedBU`) and by Exposure.
- **Table:** linked AzureID, Title, Severity, Query, Emergency, Aging, Due Status, Manager, Tribe, ReportDate, DueDate and Extended Target Date. Includes text search and CSV export.
- **CSS-only hamburger filter menu** that applies to the whole report: Emergency, Tribe, period, Manager, AzureID, Title, Brand, Due Status, Exposure, Query, Detection Source and SLA Exception.

---

## How it works

### Context files

These files are stored in the **RBVM Agent** Claude Project. The skills read them at runtime. To change the agent's behaviour, edit these files instead of the skills.

| File | Used by | Purpose |
|------|---------|---------|
| `PolicyGV.txt` | Grouping | Defines the Tenable queries based on the Vulnerability Management Policy |
| `Severity.txt` | Grouping | Maps the source query to an emergency level |
| `SLA.txt` | Grouping, Orchestrator | Remediation deadline (calendar days counted from today) |
| `Mitigations.txt` | Grouping | List of contingency compensatory controls, used in addition to an official mitigation measure, where one exists. |
| `AreaPath.txt` | Orchestrator | Maps each team based on Tenable TAG (`CORE_TEAM`) to its **Tribe**, **Azure Area Path** and **Manager e-mail**. Fills `Assigned To`, `V_Tribe1` and `Area Path` on every card. Add a row here whenever a new team appears. |
| `status-change-criteria.md` | Orchestrator (inside the skill) | Decision tree for creating, reactivating, replacing and closing cards. |

### Database (`agent_output.db`)

Each `queryN` table has a primary key plus these columns:

```
AzureID | FindingID | Title | Description | Assets | Evidence | ResponsibleTeam | Solution |
Mitigation | References | Severity | RemediationDeadline | SourceQuery | PendingItems |
Alert30 | Alert15 | Alert5 | CreatedDate | ClosedDate | UpdatedAt | StatusCardAzure
```

- `FindingID`: the deduplication key between collections.
- `PendingItems`: drives the decision to close a card.
- `StatusCardAzure`: mirrors the state of the Azure DevOps card.
- `Alert30`, `Alert15`, `Alert5`: reserved for SLA reminders at 30, 15 and 5 days before the deadline.

---

## Prerequisites

- **Claude desktop app** (Cowork), with a Claude Project named **RBVM Agent** that holds the files in `context/`.
- **Tenable Vulnerability Management** (or Tenable One) with access to Hexa AI, and a Tenable API access key and secret key. They go in the `X-ApiKeys` header of `mcp-config/mcp-config.json`.
- **Node.js**: the Tenable and Azure DevOps MCP servers are started with `npx`.
- **Python** with a virtual environment, to run the local SQLite MCP server in `mcp-sqlite/` (see `mcp-sqlite/README.md`).
- **Azure CLI** signed in with `az login`, because the Azure DevOps MCP server is configured with `--authentication azcli`.
- **Azure DevOps** organization with a *Vulnerability* work item type, permission to create, update and comment on work items in the Area Paths listed in `context/AreaPath.txt`, and read access to Analytics (OData).

---

## Setup

1. **Claude Project:** open the **RBVM Agent** project in Claude (Cowork) and confirm that the context files listed above are in it.
2. **Skills:** enable the four skills on your account. Each folder also contains a `.zip` of the same skill for upload. The name Claude shows is the `name:` value in the skill's `SKILL.md`:

   | Folder | Skill name in `SKILL.md` |
   |--------|--------------------------|
   | `skill-policy-based-grouping/vm-policy-based-vulnerability-grouping` | `vm-policy-based-vulnerability-grouping` |
   | `skill-save-data-on-sqlite3-database/vm-save-data-on-sqlite3-database` | `vm-save-data-on-sqlite-database` |
   | `skill-azuredevops-vulnerability-orchestrator/vm-azuredevops-vulnerability-orchestrator` | `vm-azuredevops-vulnerability-orchestrator` |
   | `skill-generate-html-dashboard/vm-vulnerability-analytics-dashboard` | `vm-vulnerability-analytics-dashboard` |
3. **MCP servers** (local, through the Claude desktop app - **See the mcp-config.json file**):
   - **Tenable** MCP: access to Tenable VM / Tenable One and HexaAI. Log in to the console when the agent asks you to.
   - **sqlite3** MCP (`sqlite-output`): points to `agent_output.db`.
   - **Azure DevOps** MCP (`ado`): needs permission to create, update and comment on *Vulnerability* work items in the Area Paths listed in `AreaPath.txt`, plus read access to Analytics (OData).
4. **Run the workflow** in order, either by asking Claude for each step or by chaining the steps:
   1. *"Run [VM] policy-based grouping"*
   2. *"Save the grouping to the database"*.
   3. *"Sync the database with Azure DevOps"*.
   4. *"Build the vulnerability dashboard"*.
5. **Review:** check the grouped cards and the Azure DevOps cards before each run that writes to production. Update the context files whenever the VM Standard, SLAs, teams or mitigation tools change.

---

## Outbound data flows

All network traffic goes through the MCP servers declared in `mcp-config/mcp-config.json`. The repository's own code (`mcp-sqlite/server.py`) makes no network calls.

| Destination | Through | What it does |
|-------------|---------|--------------|
| Tenable cloud (`https://cloud.tenable.com/mcp/`) | `mcp-remote` | Reads vulnerability findings, assets and tags with your Tenable API keys |
| Your Azure DevOps organization | `@azure-devops/mcp` (Azure CLI login) | Creates, updates and comments on *Vulnerability* work items; reads Analytics (OData) for the dashboard |
| Local SQLite file (`SQLITE_OUTPUT_DB`) | `mcp-sqlite/server.py` over stdio | Stores the grouped findings on your computer |

The findings these tools return are processed by Claude as part of the conversation.

---

## Known limitations

- **Company-specific context.** The queries in `PolicyGV.txt`, the SLAs, severity map, mitigations list and team map in `context/` are samples. Replace them with your own standard before running the agent.
- **Team assignment.** Grouping and card assignment rely on the `CORE_TEAM` tag in Tenable and on a matching row in `AreaPath.txt`. Add a row whenever a new team appears. Replace them with your own standard before running the agent.
- **Azure DevOps process.** The orchestrator assumes a *Vulnerability* work item type with custom fields such as `V_Tribe1` and `V_ImpactedBU`. Other processes need the orchestrator skill adapted. Replace them with your own standard before running the agent.
- **Fixed number of queries.** The database has seven tables, `query1` to `query7`, matching the seven policy queries.
- **No SLA reminders yet.** `Alert30`, `Alert15` and `Alert5` are reserved columns. No reminder automation is included.
- **Windows-oriented setup.** The example config uses `C:/` paths and `venv/Scripts/python.exe`, and `mcp-sqlite/requirements.txt` includes `pywin32`. On macOS or Linux, adapt the paths and remove that dependency.
- **Dashboard needs the Azure DevOps MCP.** If that connection fails, the dashboard is not built.
- **LLM-driven.** Review the grouped cards and the Azure DevOps cards before each run that writes to production.
- This agent was based on the following technologies that can be adapted to your own scenario:
  - **ITSM**: AzureDevOps.
  - **Local Database**: SQLite3
