from models import MarketSnapshot, AgentOutput


async def run(
    ticker: str,
    snapshot: MarketSnapshot
) -> AgentOutput:

    return AgentOutput.unavailable(
        "fundamental",
        ticker,
        (
            "Fundamental filing data is not available in the "
            "current market snapshot. Fundamental analysis "
            "requires filing evidence."
        )
    )