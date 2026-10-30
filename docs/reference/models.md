# Модели

Все модели экспортируются из `cdekx.models`. Схемы сверены с
OpenAPI-спецификацией apidoc.cdek.ru (секция `api_v2_integration`).

## Базовые и конверты ответов

::: cdekx.models.base.CdekModel

::: cdekx.models.base.ResponseEnvelope

::: cdekx.models.base.ListResponse

::: cdekx.models.base.RequestInfo

::: cdekx.models.base.RelatedEntity

::: cdekx.models.base.ErrorInfo

::: cdekx.models.base.RequestState

## Общие структуры

::: cdekx.models.common.Phone

::: cdekx.models.common.Contact

::: cdekx.models.common.Money

::: cdekx.models.common.DeliveryCostThreshold

::: cdekx.models.common.Location

::: cdekx.models.common.Package

::: cdekx.models.common.PackageResponse

::: cdekx.models.common.Item

::: cdekx.models.common.Service

::: cdekx.models.common.Seller

## Заказы

::: cdekx.models.orders.OrderCreate

::: cdekx.models.orders.OrderUpdate

::: cdekx.models.orders.Order

::: cdekx.models.orders.OrderStatus

::: cdekx.models.orders.DeliveryDetail

::: cdekx.models.orders.OrderNumberQuery

## Калькулятор

::: cdekx.models.calculator.TariffRequest

::: cdekx.models.calculator.TariffListRequest

::: cdekx.models.calculator.TariffWithServicesRequest

::: cdekx.models.calculator.TariffCalculation

::: cdekx.models.calculator.TariffListResponse

::: cdekx.models.calculator.TariffCodeItem

::: cdekx.models.calculator.AvailableTariffsResponse

::: cdekx.models.calculator.CalculatorLocation

::: cdekx.models.calculator.CalculatorPackage

## Локации и ПВЗ

::: cdekx.models.locations.City

::: cdekx.models.locations.CityQuery

::: cdekx.models.locations.CityByCoordinates

::: cdekx.models.locations.Region

::: cdekx.models.locations.Postcodes

::: cdekx.models.locations.SuggestCity

::: cdekx.models.delivery.DeliveryPoint

::: cdekx.models.delivery.DeliveryPointFilter

::: cdekx.models.delivery.DeliveryPointPolygonFilter

::: cdekx.models.delivery.OfficeLocation

## Договорённость о доставке

::: cdekx.models.delivery_agreement.DeliveryAgreement

::: cdekx.models.delivery_agreement.DeliveryAgreementInfo

::: cdekx.models.delivery_agreement.AvailableIntervalsResponse

::: cdekx.models.delivery_agreement.EstimatedIntervalsRequest

## Заявки на вызов курьера

::: cdekx.models.intakes.Intake

::: cdekx.models.intakes.IntakeInfo

::: cdekx.models.intakes.IntakePackage

::: cdekx.models.intakes.IntakeStatusChange

::: cdekx.models.intakes.IntakeAvailableDaysRequest

## Печать

::: cdekx.models.print.WaybillCreate

::: cdekx.models.print.BarcodeCreate

::: cdekx.models.print.PrintOrder

::: cdekx.models.print.Waybill

::: cdekx.models.print.Barcode

::: cdekx.models.print.WaybillFormType

## Вебхуки

::: cdekx.models.webhooks.WebhookCreate

::: cdekx.models.webhooks.Webhook

## Прочие разделы: чеки, паспорта, реестры, фото, преалерты, реверс

Ответы этих методов приходят «списком с ошибками»
([`ListResponse`][cdekx.models.base.ListResponse]), а не конвертом.

::: cdekx.models.misc.CheckResponse

::: cdekx.models.misc.CheckInfo

::: cdekx.models.misc.PassportResponse

::: cdekx.models.misc.PassportOrder

::: cdekx.models.misc.RegistriesResponse

::: cdekx.models.misc.Registry

::: cdekx.models.misc.PhotoRequest

::: cdekx.models.misc.PhotoResponse

::: cdekx.models.misc.PhotoReadyOrder

::: cdekx.models.misc.PrealertCreate

::: cdekx.models.misc.Prealert

::: cdekx.models.misc.PrealertPackageInfo

::: cdekx.models.misc.RestrictionRequest

::: cdekx.models.misc.RestrictionItem

::: cdekx.models.misc.RestrictionHintsResponse

::: cdekx.models.misc.PackageHint

::: cdekx.models.misc.HintStatus

::: cdekx.models.misc.ReverseValidateRequest

::: cdekx.models.misc.ReverseContragent

::: cdekx.models.misc.ReverseLocation

## Перечисления

::: cdekx.types.enums
