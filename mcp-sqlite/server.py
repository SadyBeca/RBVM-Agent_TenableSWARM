"""
MCP server for the agent to store vulnerability findings in SQLite.
Database containing 7 identical tables (Query1 ... Query7). Exposed interface:
  - create_entry  -> creates a record (parameterized INSERT)
  - update_entry  -> the only UPDATE operation: limited to fields that remain editable after creation
  - list_entries  -> lists summarized records from a table
  - read_entry    -> retrieves the full details of a record
No free-form SQL, DELETE operations, or DDL commands are exposed to the agent. 
The table name is selected from a fixed list (SQL identifiers cannot be parameterized), and values are always passed as parameters.
"""

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer

DB_PATH = Path(os.environ.get("SQLITE_OUTPUT_DB", "agent_output.db")).expanduser().resolve()

TABLES = tuple(f"Query{i}" for i in range(1, 8))
TableName = Literal["Query1", "Query2", "Query3", "Query4", "Query5", "Query6", "Query7"]

NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%SZ','now')"  # UTC
MAX_LIST = 500

mcp = MCPServer("sqlite-output")


def _connect(readonly: bool = False) -> sqlite3.Connection:
    uri = f"file:{DB_PATH}?mode={'ro' if readonly else 'rwc'}"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    if readonly:
        conn.execute("PRAGMA query_only = ON")
    return conn


def _create_table_sql(table: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS "{table}" (
        EntryId      INTEGER PRIMARY KEY AUTOINCREMENT,
        AzureID          INTEGER,
        FindingID        TEXT NOT NULL,
        Title           TEXT NOT NULL,
        Description        TEXT NOT NULL,
        Assets           TEXT NOT NULL,
        Evidence       TEXT NOT NULL,
        ResponsibleTeam   TEXT NOT NULL,
        Solution          TEXT NOT NULL,
        Mitigation        TEXT NOT NULL,
        _References      TEXT NOT NULL,
        Severity       TEXT NOT NULL,
        RemediationDeadline DATETIME NOT NULL,
        SourceQuery      TEXT NOT NULL,
        PendingItems       TEXT NOT NULL,
        Alert30         DATETIME,
        Alert15         DATETIME,
        Alert5          DATETIME,
        CreatedDate      DATETIME NOT NULL DEFAULT ({NOW_SQL}),
        ClosedDate       DATETIME,
        UpdatedAt        DATETIME NOT NULL DEFAULT ({NOW_SQL}),
        StatusCardAzure  TEXT
    )
    """


def _init_db() -> None:
    with closing(_connect()) as conn, conn:
        for t in TABLES:
            conn.execute(_create_table_sql(t))
            conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{t}_azure" ON "{t}"(AzureID)')
            conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{t}_finding" ON "{t}"(FindingID)')


def _check_table(table: str) -> str:
    if table not in TABLES:
        raise ValueError(f"table must be one of: {', '.join(TABLES)}")
    return table


@mcp.tool()
def create_entry(
    table: TableName,
    FindingID: str,
    Title: str,
    Description: str,
    Assets: str,
    Evidences: str,
    ResponsibleTeam: str,
    Solution: str,
    Mitigation: str,
    References: str,
    Severity: str,
    RemediationDeadline: str,
    SourceQuery: str,
    PendingItems: str,
) -> dict:
    """
    Creates a record in one of the Query1 through Query7 tables.
    AzureID, StatusCardAzure, ClosedDate, and Alert30/15/5 are initially set to null and are populated later using update_entry.
    EntryID, CreatedDate, and UpdatedAt are generated automatically (UTC dates in ISO 8601 format).
    Args:
    table: Query1 through Query7.
    FindingID: identifier of the finding in the source system.
    Title: finding title.
    Description: finding description.
    Assets: affected assets.
    Evidences: collected evidence.
    ResponsibleTeam: team responsible for remediation.
    Solution: recommended solution.
    Mitigation: possible mitigation while the solution has not yet been implemented.
    References: references (CVEs, links, etc.).
    Severity: finding severity.
    RemediationDeadline: SLA expiration date (e.g., 2026-12-31T23:59:59Z).
    SourceQuery: query from which the finding originated.
    PendingItems: outstanding open items.
    """
    _check_table(table)
    cols = (
        "FindingID", "Title", "Description", "Assets", "Evidences", "ResponsibleTeam",
        "Solution", "Mitigation", "References", "Severity", "RemediationDeadline",
        "SourceQuery", "PendingItems",
    )
    values = (
        FindingID, Title, Description, Assets, Evidences, ResponsibleTeam,
        Solution, Mitigation, References, Severity, RemediationDeadline,
        SourceQuery, PendingItems,
    )
    sql = f'INSERT INTO "{table}" ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})'
    with closing(_connect()) as conn, conn:
        cur = conn.execute(sql, values)
        return {"table": table, "EntryId": cur.lastrowid, "status": "created"}


@mcp.tool()
def update_entry(
    table: TableName,
    EntryId: int,
    PendingItems: str | None = None,
    AzureID: str | None = None,
    StatusCardAzure: str | None = None,
    ClosedDate: str | None = None,
    Alert30: str | None = None,
    Alert15: str | None = None,
    Alert5: str | None = None,
    UpdatedAt: str | None = None,
) -> dict:
    """
    Updates the editable fields of an existing record. All other fields remain unchanged.
    At least one field must be provided for update. Any omitted field will retain its current value.
    An empty string ("") clears fields that accept null values (AzureID, StatusCardAzure,
    ClosedDate, Alert30, Alert15, Alert5).
    UpdatedAt is automatically set to the current UTC timestamp; only provide a value if you want to override it with a different timestamp.

    Args:
        table: Query1 a Query7.
        EntryId: id do registro.
        PendingItems: novas pendências (substitui o texto anterior).
        AzureID: ID do work item no Azure DevOps.
        StatusCardAzure: status atual do card no Azure DevOps.
        ClosedDate: data de fechamento.
        Alert30: marca/data do alerta de 30 dias.
        Alert15: marca/data do alerta de 15 dias.
        Alert5: marca/data do alerta de 5 dias.
        UpdatedAt: valor explícito para UpdatedAt (opcional).
    """
    _check_table(table)
    sets: list[str] = []
    params: list = []

    if PendingItems is not None:
        sets.append("PendingItems = ?")
        params.append(PendingItems)

    # Campos que aceitam nulo: "" vira NULL. Nomes de coluna fixos, só valores como parâmetro.
    for col, val in (
        ("AzureID", AzureID),
        ("StatusCardAzure", StatusCardAzure),
        ("ClosedDate", ClosedDate),
        ("Alert30", Alert30),
        ("Alert15", Alert15),
        ("Alert5", Alert5),
    ):
        if val is not None:
            sets.append(f"{col} = ?")
            params.append(val.strip() or None)

    if not sets and UpdatedAt is None:
        raise ValueError(
            "You can only edit one of these fields: PendingItems, AzureID, StatusCardAzure, "
            "ClosedDate, Alert30, Alert15, Alert5 ou UpdatedAt"
        )

    if UpdatedAt is not None and UpdatedAt.strip():
        sets.append("UpdatedAt = ?")
        params.append(UpdatedAt.strip())
    else:
        sets.append(f"UpdatedAt = {NOW_SQL}")

    params.append(EntryId)
    sql = f'UPDATE "{table}" SET {", ".join(sets)} WHERE EntryId = ?'
    with closing(_connect()) as conn, conn:
        cur = conn.execute(sql, params)
        if cur.rowcount == 0:
            raise ValueError(f"registro {EntryId} não encontrado em {table}")
    return read_entry(table, EntryId)


@mcp.tool()
def list_entries(
    table: TableName,
    no_azure_id: bool = False,
    Severity: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """    
    Lists the most recent records from a table in a summarized format.
    To view all fields of a record, use read_entry.

    Args:
        table: Query1 a Query7.
        no_azure_id: se verdadeiro, traz só registros com AzureID nulo.
        Severity: se informado, filtra pela Severity.
        limit: quantidade máxima de registros (1 a 500).
    """
    _check_table(table)
    limit = max(1, min(limit, MAX_LIST))
    sql = (
        "SELECT EntryId, AzureID, FindingID, Title, Severity, RemediationDeadline, "
        "StatusCardAzure, ClosedDate, UpdatedAt "
        f'FROM "{table}"'
    )
    where, params = [], []
    if no_azure_id:
        where.append("AzureID IS NULL")
    if Severity:
        where.append("Severity = ?")
        params.append(Severity)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY EntryId DESC LIMIT ?"
    params.append(limit)
    with closing(_connect(readonly=True)) as conn:
        return [dict(r) for r in conn.execute(sql, params)]


@mcp.tool()
def read_entry(table: TableName, EntryId: int) -> dict:
    """Reads a complete record (all fields) by its EntryId."""
    _check_table(table)
    with closing(_connect(readonly=True)) as conn:
        row = conn.execute(
            f'SELECT * FROM "{table}" WHERE EntryId = ?', (EntryId,)
        ).fetchone()
    if row is None:
        raise ValueError(f"registry {EntryId} not found in {table}")
    return dict(row)


if __name__ == "__main__":
    _init_db()
    mcp.run()  # transporte stdio
