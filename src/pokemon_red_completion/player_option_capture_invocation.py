"""Prospective capture invocation facts, never an outcome or success forecast."""
from dataclasses import asdict, dataclass

CAPTURE_INVOCATION_SCHEMA = "pokemon.core.option-capture-invocation.v1"
CAPTURE_INVOCATION_NAMES = ("present", "paid_finite_search", "encounter_cap", "complete_paid_session")


@dataclass(frozen=True, slots=True)
class OptionCaptureInvocation:
    maximum_encounters: int
    complete_paid_session: bool
    mechanism: str = "paid_finite_search"

    def __post_init__(self):
        if type(self.maximum_encounters) is not int or self.maximum_encounters <= 0:
            raise ValueError("capture invocation requires a resolved positive encounter cap")
        if type(self.complete_paid_session) is not bool:
            raise ValueError("capture invocation requires an explicit lifecycle")
        if type(self.mechanism) is not str or self.mechanism != "paid_finite_search":
            raise ValueError("capture invocation mechanism is unsupported")

    def vector(self):
        # A fixed bounded count projection; it does not estimate encounter yield.
        cap = self.maximum_encounters
        return (1., 1., cap / (cap + 100), float(self.complete_paid_session))

    def public_dict(self):
        return dict(schema=CAPTURE_INVOCATION_SCHEMA, **asdict(self))

    @classmethod
    def from_public(cls, document):
        names = set(cls.__dataclass_fields__)
        if (not isinstance(document, dict) or set(document) != names | {"schema"}
                or document["schema"] != CAPTURE_INVOCATION_SCHEMA):
            raise ValueError("capture invocation document differs")
        return cls(**{name: document[name] for name in names})


def capture_invocation_feature_names():
    return tuple("capture_invocation." + name for name in CAPTURE_INVOCATION_NAMES)


def capture_invocation_vector(invocation):
    return (0.,) * len(CAPTURE_INVOCATION_NAMES) if invocation is None else invocation.vector()


COMPLETE_PAID_CAPTURE_NAMES = ("complete_paid", "complete_paid_x_encounter_cap")


def complete_paid_capture_feature_names():
    return tuple("capture_scope." + name for name in COMPLETE_PAID_CAPTURE_NAMES)


def complete_paid_capture_vector(invocation_vector, *, acquire):
    """Derive the local gate before any learned normalization or centering."""
    import math
    from numbers import Real

    values = tuple(invocation_vector)
    if (type(acquire) is not bool or len(values) != len(CAPTURE_INVOCATION_NAMES)
            or any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) for v in values)):
        raise ValueError("complete-paid capture input differs")
    if values == (0., 0., 0., 0.):
        return (0., 0.)
    present, paid, horizon, complete = values
    if (not acquire or present != 1. or paid != 1.
            or not 0. < horizon <= 1. or complete not in (0., 1.)):
        raise ValueError("complete-paid capture invocation differs")
    return (1., float(horizon)) if complete == 1. else (0., 0.)


COMPLETE_PAID_DENSITY_NAMES = (
    "complete_paid_x_uncertainty", "complete_paid_x_encounter_cap_x_uncertainty",
)


def complete_paid_density_feature_names() -> tuple[str, ...]:
    return tuple("capture_scope." + name for name in COMPLETE_PAID_DENSITY_NAMES)


def complete_paid_density_vector(complete_paid_vector, *, uncertainty) -> tuple[float, float]:
    """Input-only products; the whole correction vanishes outside the paid gate."""
    import math
    from numbers import Real
    values = tuple(complete_paid_vector)
    if (len(values) != 2 or any(isinstance(v, bool) or not isinstance(v, Real)
                               or not math.isfinite(v) for v in values)
            or isinstance(uncertainty, bool) or not isinstance(uncertainty, Real)
            or not math.isfinite(uncertainty) or not 0. <= uncertainty <= 1.):
        raise ValueError("complete-paid density inputs differ")
    if values == (0., 0.):
        return (0., 0.)
    gate, horizon = values
    if gate != 1. or not 0. < horizon <= 1.:
        raise ValueError("complete-paid density gate differs")
    return (float(uncertainty), float(horizon * uncertainty))
