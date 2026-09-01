from dataclasses import dataclass, field


@dataclass(slots=True)
class ProcessingError(Exception):
    code: str
    message: str
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }

