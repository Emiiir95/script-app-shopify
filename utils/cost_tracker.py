# Prix gpt-4o-mini ($/million de tokens)
PRICE_INPUT_PER_M  = 0.150
PRICE_OUTPUT_PER_M = 0.600


class CostTracker:
    def __init__(self):
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
            self.total_input_tokens  / 1_000_000 * PRICE_INPUT_PER_M +
            self.total_output_tokens / 1_000_000 * PRICE_OUTPUT_PER_M
        )

    def summary(self):
        return (
            f"Appels OpenAI : {self.calls} | "
            f"Tokens entrée : {self.total_input_tokens} | "
            f"Tokens sortie : {self.total_output_tokens} | "
            f"Coût estimé : ${self.cost_usd:.4f} USD"
        )
