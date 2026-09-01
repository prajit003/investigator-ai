# Investigator AI Architecture

## 1. The Four Agents and Their Roles
1. **Technical Agent**: Analyzes price action, volume trends, moving averages, and momentum indicators to determine short-term entry/exit signals.
2. **Fundamental Agent**: Evaluates financial statements, earnings growth, valuation multiples (P/E, EV/EBITDA), and balance sheet health.
3. **Sentiment Agent**: Processes news headlines, social media chatter, and analyst upgrades/downgrades to gauge market perception.
4. **Judge Agent**: Consolidates the outputs from the other agents to make a final directional verdict (e.g., STRONG_POSITIVE, POSITIVE, CAUTION, NEGATIVE, INSUFFICIENT_DATA) before the synthesis layer personalizes the recommendation.

## 2. Orchestration + Timeout/Degradation Model
The system uses an asynchronous fan-out/fan-in orchestration model. The initial request is broadcast to all specialized agents (Technical, Fundamental, Sentiment) simultaneously. 
- **Timeouts**: Each agent has a strict timeout (e.g., 5 seconds). 
- **Degradation**: If an agent fails to respond within the timeout or errors out, its status is marked as `UNAVAILABLE`. The Judge Agent and Synthesis Layer proceed with the available data, ensuring the system degrades gracefully rather than failing completely.

## 3. RAG Grounding Enforcement
Retrieval-Augmented Generation (RAG) is enforced across all agents to prevent hallucinations.
- Agents cannot make assertions without citing retrieved documents.
- Prompts are strictly constrained to only use provided context.
- The Synthesis layer does not hallucinate new financial data; it only reasons over the explicit outputs provided by the agents and the user's defined profile.

## 4. How Profiles Change Output
The Synthesis Layer applies deterministic, rule-based logic to tailor recommendations based on the user's `UserProfile`:
- **Conservative Profiles**: Confidence is capped to prevent over-reliance on bullish signals. Requires stronger consensus (e.g., >=2 BULLISH agents) and strictly downgrades to HOLD if the portfolio concentration is too high (e.g., >25%). Any strong dissenting bearish signal blocks a BUY.
- **Aggressive Profiles**: Tolerates higher portfolio concentration and dissenting opinions. A single high-confidence BULLISH agent can trigger a BUY recommendation, even if a bearish agent dissents.

## 5. Three Metrics Logged Per Session
1. **Agent Latency**: Response times for each individual agent (Technical, Fundamental, Sentiment) to monitor bottlenecks.
2. **Fallback / Degradation Rate**: The frequency of agents timing out or failing (resulting in `UNAVAILABLE` status) and the system relying on partial data.
3. **Recommendation Conversion (Rule vs. LLM)**: Tracking whether the synthesis layer successfully utilized the LLM for rationale generation or if it fell back to rule-based strings.
