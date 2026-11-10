---
name: "vm-save-data-on-sqlite3-database"
description: Saves the grouped data obtained from the Hexa AI skill into the database through the sqlite3 MCP.
---
 
## Tools
 
sqlite3 MCP and the vulnerability grouping output.
 
## First-time save
 
The database is agent_output.db.
You must save the result of each query in a separate table, and each table must be named:
Query1
Query2
Query3
Query4
Query5
Query6
Query7
 
The Hexa table will have the following fields:
 
ID | FindingID | Title | Description | Assets | Evidence | ResponsibleTeam | Solution | Mitigation | References | Severity | RemediationDeadline | SourceQuery | PendingItems 
 
Save to the database following this mapping:
 
| DatabaseField | HexaOutputField |
|---------------|-----------------|
| AzureID | Null until the card is created |
| FindingID | Hexa "Findings IDs" field |
| Title | Hexa "Title" field |
| Description| Hexa "Description" field |
| Assets| Hexa "Assets" field |
| Evidence | Hexa "Evidence" field |
| ResponsibleTeam | Hexa "ResponsibleTeam" field |
| Solution| Hexa "Solution" field |
| Mitigation| Hexa "Mitigation" field |
| _References| Hexa "References" field |
| Severity | Hexa "Severity" field |
| RemediationDeadline | Hexa "RemediationDeadline" field |
| SourceQuery | Hexa "SourceQuery" field |
| PendingItems| Hexa "PendingItems" field |
| Alert30| Null at the start |
| Alert15 | Null at the start |
| Alert5 | Null at the start |
| CreatedDate | Null at the start; creation date of the AzureID card |
| ClosedDate | Null at the start; closing date of the AzureID card |
| UpdatedAt | Every time the record is updated |
| StatusCardAzure | Null; updated when the Azure card is created |
 
## Saving in subsequent iterations
 
After the first run, in the following runs:
 
- Compare the Hexa AI output with what already exists in the agent_output.db tables.
- Compare the result of each query with the table of the same name. Example: Query 1 → Query1 table.
- Compare the Findings IDs fields with the database FindingID field.
- For Hexa AI records whose findings already exist in a database record with StatusCardAzure other than Closed, do not create new records.
- For Hexa records that have no matching record in the database, create one in the database.
- The field mapping remains the same as in "First-time save".