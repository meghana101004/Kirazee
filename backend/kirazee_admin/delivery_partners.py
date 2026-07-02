from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from kirazee_app.models import Registration, Business
from delivery.models import DeliveryPartner
from delivery.serializers import DeliveryPartnerSerializer


class BusinessDeliveryPartnersView(APIView):
    """
    Admin service to manage delivery partners for a specific business.

    - POST /admin/businesses/<business_id>/delivery-partners/  -> create
      Body: { user_id, phone_number, vehicle_type, vehicle_number, is_available?, status? }

    - PATCH /admin/businesses/<business_id>/delivery-partners/<int:partner_id>/ -> update
      Body: any of { phone_number, vehicle_type, vehicle_number, is_available, status, latitude, longitude }

    - DELETE /admin/businesses/<business_id>/delivery-partners/<int:partner_id>/ -> delete
    """

    permission_classes = []

    def get(self, request, business_id):
        """Get all delivery partners for a specific business"""
        # Validate business exists
        get_object_or_404(Business, business_id=business_id)
        
        partners = DeliveryPartner.objects.filter(business_id=business_id)
        serializer = DeliveryPartnerSerializer(partners, many=True)
        
        return Response({
            "success": True,
            "message": f"Found {len(partners)} delivery partners",
            "partners": serializer.data
        }, status=status.HTTP_200_OK)

    @staticmethod
    def _to_bool(val, default=None):
        if isinstance(val, bool):
            return val
        if val is None:
            return default
        if isinstance(val, (int, float)):
            return bool(int(val))
        if isinstance(val, str):
            v = val.strip().lower()
            if v in {"1", "true", "yes", "on"}:
                return True
            if v in {"0", "false", "no", "off"}:
                return False
        return default

    def post(self, request, business_id):
        # Validate business exists
        get_object_or_404(Business, business_id=business_id)

        user_id = request.data.get("user_id")
        phone_number = request.data.get("phone_number")
        vehicle_type = request.data.get("vehicle_type")
        vehicle_number = request.data.get("vehicle_number")
        is_available = self._to_bool(request.data.get("is_available"), default=True)
        # allow both 'is_verified' and the common misspelling 'is_varified'
        is_verified = self._to_bool(
            request.data.get("is_verified", request.data.get("is_varified")),
            default=False,
        )
        # status is treated as boolean from client; map to model choices later
        status_bool = self._to_bool(request.data.get("status"), default=False)

        # Basic validations
        if not user_id or not phone_number or not vehicle_type or not vehicle_number:
            return Response({
                "success": False,
                "message": "user_id, phone_number, vehicle_type, vehicle_number are required"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Ensure user exists
        user = get_object_or_404(Registration, user_id=user_id)

        # One delivery partner per Registration enforced by OneToOne; guard early
        if DeliveryPartner.objects.filter(user_id=user.user_id).exists():
            return Response({
                "success": False,
                "message": "Delivery partner already exists for this user"
            }, status=status.HTTP_409_CONFLICT)

        # Convert boolean status to numeric-like string values ('1' for available, '0' for offline)
        status_norm = '1' if status_bool else '0'

        partner = DeliveryPartner.objects.create(
            user=user,
            business_id=business_id,
            vehicle_type=vehicle_type,
            vehicle_number=vehicle_number,
            phone_number=phone_number,
            is_available=is_available,
            is_verified=is_verified,
            status=status_norm,
        )

        return Response({
            "success": True,
            "message": "Delivery partner created",
            "partner": DeliveryPartnerSerializer(partner).data
        }, status=status.HTTP_201_CREATED)

    def patch(self, request, business_id, partner_id):
        # Fetch partner by id, then verify it belongs to the provided business_id
        partner = get_object_or_404(DeliveryPartner, id=partner_id)
        if str(partner.business_id) != str(business_id):
            return Response({
                "success": False,
                "message": "Delivery partner does not belong to the specified business_id",
                "partner_business_id": partner.business_id,
                "requested_business_id": business_id
            }, status=status.HTTP_400_BAD_REQUEST)

        updatable = {
            "phone_number": str,
            "vehicle_type": str,
            "vehicle_number": str,
            "is_available": bool,
            "is_verified": bool,
            "status": bool,
            "latitude": float,
            "longitude": float,
        }

        data = request.data or {}
        changed = False

        for field, caster in updatable.items():
            if field in data:
                value = data.get(field)
                try:
                    if caster is bool:
                        value = self._to_bool(value)
                    elif caster is float and value is not None:
                        value = float(value)
                    elif caster is str and value is not None:
                        value = str(value)
                except Exception:
                    return Response({
                        "success": False,
                        "message": f"Invalid value for {field}"
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Special handling: boolean 'status' maps to model choice
                if field == 'status':
                    # None means ignore
                    if value is not None:
                        partner.status = '1' if value else '0'
                        changed = True
                    continue

                setattr(partner, field, value)
                changed = True

        # Optional reassignment protection: do not allow changing business_id via this API
        # If needed in future, add explicit route to transfer partner between businesses.

        if changed:
            partner.save()

        return Response({
            "success": True,
            "message": "Delivery partner updated" if changed else "No changes",
            "partner": DeliveryPartnerSerializer(partner).data
        }, status=status.HTTP_200_OK)

    def delete(self, request, business_id, partner_id):
        partner = get_object_or_404(DeliveryPartner, id=partner_id)
        if str(partner.business_id) != str(business_id):
            return Response({
                "success": False,
                "message": "Delivery partner does not belong to the specified business_id",
                "partner_business_id": partner.business_id,
                "requested_business_id": business_id
            }, status=status.HTTP_400_BAD_REQUEST)
        partner.delete()
        return Response({
            "success": True,
            "message": "Delivery partner deleted",
            "partner_id": partner_id,
            "business_id": business_id
        }, status=status.HTTP_200_OK)

