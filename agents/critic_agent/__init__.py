from .run import run_critics

# Expose run_critics under two names for backward compatibility
run_all = run_critics

__all__ = ["run_critics", "run_all"]
