"""The MCP server, driven through a real MCP client — in-process, and over
stdio exactly as Claude Desktop / Claude Code would launch it."""
import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

from backend.mcp_server import mcp as server

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = str(ROOT / "data" / "transactions.csv")


def call(tool, args, target=server):
    async def go():
        async with Client(target) as c:
            return await c.call_tool(tool, args)
    return asyncio.run(go())


def test_lists_tools_and_policy():
    async def go():
        async with Client(server) as c:
            listed = (await c.list_tools()).tools
            assert all(t.output_schema for t in listed)  # typed results for agents
            tools = {t.name for t in listed}
            policy = await c.read_resource("finguard://policy")
            return tools, policy
    tools, policy = asyncio.run(go())
    assert {"check_transaction", "screen_transactions", "screen_csv", "verify_audit_trail"} <= tools
    assert "Structuring" in policy.contents[0].text


def test_check_transaction():
    r = call("check_transaction", {"transaction": {
        "date": "2024-03-22", "time": "02:01", "account": "ACC001", "beneficiary": "FastCash",
        "description": "transfer", "amount": 49800, "type": "debit"}})
    out = r.structured_content
    assert out["worst_severity"] == "HIGH" and set(out["checks"]) == {"late_night", "unknown_beneficiary", "structuring"}
    assert all(c["triggered"] for c in out["checks"].values())


def test_screen_csv_matches_the_api_pipeline():
    out = call("screen_csv", {"path": SAMPLE}).structured_content
    assert out["transactions"] == 200 and out["overall_risk"] in {"LOW", "MEDIUM", "HIGH"}
    assert out["flagged_transactions"][0]["worst_severity"] == "HIGH"


def test_bad_input_is_a_tool_error_not_a_crash():
    r = call("screen_csv", {"path": str(ROOT / "backend" / "main.py")})
    assert r.is_error


def test_stdio_entry_point():
    params = StdioServerParameters(command=sys.executable, args=["-m", "backend.mcp_server"], cwd=str(ROOT))
    out = call("screen_csv", {"path": SAMPLE}, target=params).structured_content
    assert out["transactions"] == 200
