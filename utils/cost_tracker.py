# Prix par million de tokens (source : OpenAI, 2026-01)
PRICING = {
    "gpt-4o-mini": {"input": 0.150, "output": 0.600},
    "gpt-4o":      {"input": 2.500, "output": 10.000},
}

# Constantes pour le modèle par défaut (gpt-4o-mini) — utilisées dans les tests
PRICE_INPUT_PER_M  = PRICING["gpt-4o-mini"]["input"]
PRICE_OUTPUT_PER_M = PRICING["gpt-4o-mini"]["output"]


class CostTracker:
    def __init__(self, model="gpt-4o-mini"):
        prices = PRICING.get(model, PRICING["gpt-4o-mini"])
        self.price_input  = prices["input"]
        self.price_output = prices["output"]
        self.model        = model
        self.total_input_tokens  = 0
        self.total_output_tokens = 0
        self.calls               = 0

    def add(self, usage):
        self.total_input_tokens  += usage.prompt_tokens
        self.total_output_tokens += usage.completion_tokens
        self.calls               += 1

    @property
    def cost_usd(self):
        return (
            self.total_input_tokens  / 1_000_000 * self.price_input +
            self.total_output_tokens / 1_000_000 * self.price_output
        )

    def summary(self):
        return (
            f"Appels OpenAI : {self.calls} | "
            f"Tokens entrée : {self.total_input_tokens} | "
            f"Tokens sortie : {self.total_output_tokens} | "
            f"Coût estimé : ${self.cost_usd:.4f} USD ({self.model})"
        )


def estimate_cost(model, input_tokens, output_tokens):
    """Retourne le coût estimé en USD pour un volume de tokens donné."""
    prices = PRICING.get(model, PRICING["gpt-4o-mini"])
    return input_tokens / 1_000_000 * prices["input"] + output_tokens / 1_000_000 * prices["output"]
