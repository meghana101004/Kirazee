# Custom swagger/Redoc metadata for Kirazee services

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Parameter:
    name: str
    in_: str  # "query", "path", "header", "body"
    required: bool
    type: str
    description: str = ""
    options: Optional[List[Any]] = None


@dataclass
class Response:
    code: int
    description: str
    example: Optional[Dict[str, Any]] = None


@dataclass
class ServiceDoc:
    name: str
    url: str
    method: str
    parameters: List[Parameter]
    response1: Optional[Response] = None
    response2: Optional[Response] = None
    response3: Optional[Response] = None
    response4: Optional[Response] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # rename "in_" back to "in" for external use
        for p in d.get("parameters", []):
            p["in"] = p.pop("in_", None)
        return d


# Example: you can add actual services here, one per endpoint
# Fill this list incrementally as we document all services.
SERVICES: List[ServiceDoc] = [
    # ServiceDoc(
    #     name="Example: Get consumer items",
    #     url="/kirazee/consumer/items",
    #     method="GET",
    #     parameters=[
    #         Parameter(
    #             name="business_id",
    #             in_="query",
    #             required=True,
    #             type="integer",
    #             description="Business ID for which to fetch items",
    #         ),
    #     ],
    #     response1=Response(
    #         code=200,
    #         description="Success",
    #         example={"status": "success", "data": []},
    #     ),
    #     response2=Response(
    #         code=400,
    #         description="Validation error",
    #         example={"status": "failed", "message": "Invalid business_id"},
    #     ),
    #     response3=Response(
    #         code=401,
    #         description="Unauthorized (-ve)",
    #         example={"status": "failed", "message": "Unauthorized"},
    #     ),
    #     response4=Response(
    #         code=500,
    #         description="Server error (-ve)",
    #         example={"status": "failed", "message": "Internal server error"},
    #     ),
    # ),
]
