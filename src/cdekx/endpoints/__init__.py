"""CDEK API resource endpoints.

Paths and schemas are verified against the OpenAPI specification published at
apidoc.cdek.ru (``scripts/fetch_openapi.py`` downloads it,
``scripts/generate_from_openapi.py`` checks the models against it).

=========================  ===================================================
Module                     Documentation section
=========================  ===================================================
``orders``                 Order operations
``calculator``             Delivery cost calculation
``locations``              City and region directories
``delivery``               Offices and pickup points (``deliverypoints``)
``delivery_agreement``     Delivery agreement and time intervals
``intakes``                Courier pickup requests
``printing``               Print forms: waybills and package barcodes
``webhooks``               Event subscriptions
``misc``                   Reverse logistics, checks, passports, registries,
                           photos, prealerts, package restrictions
=========================  ===================================================
"""

from __future__ import annotations

from .base import (
    Endpoint,
    ResponseParseError,
    parse_envelope,
    parse_list,
    parse_list_json,
    parse_model,
    parse_model_json,
    poll_until,
)
from .calculator import CalculatorEndpoint
from .delivery import DeliveryPointsEndpoint
from .delivery_agreement import DeliveryAgreementEndpoint

# TaskEnvelope is deliberately imported from orders: intakes declares exactly the
# same envelope (ResponseEnvelope[RootEntity]), and one structure does not need
# two names.
from .intakes import IntakeEnvelope, IntakeInfoEnvelope, IntakesEndpoint
from .locations import LocationsEndpoint
from .misc import MiscEndpoint, PrealertEnvelope, PrealertTaskEnvelope
from .orders import OrderEnvelope, OrdersEndpoint, TaskEnvelope
from .printing import PrintEndpoint
from .webhooks import WebhooksEndpoint

__all__ = [
    "CalculatorEndpoint",
    "DeliveryAgreementEndpoint",
    "DeliveryPointsEndpoint",
    "Endpoint",
    "IntakeEnvelope",
    "IntakeInfoEnvelope",
    "IntakesEndpoint",
    "LocationsEndpoint",
    "MiscEndpoint",
    "OrderEnvelope",
    "OrdersEndpoint",
    "PrealertEnvelope",
    "PrealertTaskEnvelope",
    "PrintEndpoint",
    "ResponseParseError",
    "TaskEnvelope",
    "WebhooksEndpoint",
    "parse_envelope",
    "parse_list",
    "parse_list_json",
    "parse_model",
    "parse_model_json",
    "poll_until",
]
