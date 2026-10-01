"""Errors that stop evaluation instead of becoming negative judgments."""


class JudgeConfigError(RuntimeError):
    """A configuration or route-policy failure; never an uninformative readout."""
