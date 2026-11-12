# fusion-guard: inspect
def run(_context: str):
    raise RuntimeError("Fusion Guard inspection was not injected: confirm that the project hooks are trusted and policy.json has enabled set to true. This probe did not modify the model.")
