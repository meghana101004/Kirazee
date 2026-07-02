from decimal import Decimal
from datetime import datetime, date
import logging

from django.db import transaction, connection
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_yasg.utils import swagger_auto_schema

from .models import (
    BusinessStaff,
    BusinessStaffAttendance,
    BusinessStaffSalaryPayments,
    StaffLoginLogs,
    RoleBasedNavItems,
    NavDisplayItem,
    BusinessFeaturePurchase,
)
from kirazee_app.models import Business, Registration
from .serializers import (
    BusinessStaffSerializer,
    StaffLoginSerializer,
    StaffOTPSendSerializer,
    StaffOTPVerifySerializer,
    StaffLoginLogsSerializer,
    StaffChangePasswordSerializer,
)

logger = logging.getLogger(__name__)


def _parse_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_time(value: str):
    return datetime.strptime(value, "%H:%M:%S").time()


@swagger_auto_schema(methods=['GET', 'POST'],tags=['management'])
@api_view(["GET", "POST"])
@transaction.atomic
def staff_list_create_view(request):
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "GET":
        # Check if we need to create missing payment records for existing staff
        _ensure_payment_records_exist(business)
        
        return _get_staff_list(request, business)
    elif request.method == "POST":
        return _create_staff(request, business)


def _ensure_payment_records_exist(business):
    """Create payment records for staff members who don't have them"""
    try:
        print(f"[Staff Views] Checking payment records for business: {business.business_id}")
        
        # Get all active staff for this business
        all_staff = BusinessStaff.objects.filter(business_id=business, status=True)
        print(f"[Staff Views] Found {all_staff.count()} active staff members")
        
        today = date.today()
        
        for staff in all_staff:
            # Check if this staff member has any payment records
            existing_payments = BusinessStaffSalaryPayments.objects.filter(staff_id=staff)
            print(f"[Staff Views] Staff {staff.full_name} (ID: {staff.staff_id}) has {existing_payments.count()} payment records")
            
            if not existing_payments.exists():
                # Create default payment record for current month
                salary_amount = Decimal("25000.00")  # Default salary
                
                created_payment = BusinessStaffSalaryPayments.objects.create(
                    staff_id=staff,
                    business_id=business,
                    year=today.year,
                    month=today.month,
                    salary_amount=salary_amount,
                    salary_paid=Decimal("0.00"),
                    is_paid=False,
                    remarks="Auto-created default payment record",
                )
                print(f"[Staff Views] Created payment record ID: {created_payment.payment_id} for staff {staff.staff_id}")
            else:
                print(f"[Staff Views] Staff {staff.full_name} already has payment records, skipping")
                
    except Exception as e:
        print(f"[Staff Views] Error ensuring payment records: {e}")
        import traceback
        traceback.print_exc()


def _create_staff(request, business):
    data = request.data
    required = [
        "role",
        "join_date",
        "monthly_salary",
    ]
    missing = [k for k in required if not data.get(k)]
    if missing:
        return Response({"error": f"Missing fields: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        join_date = _parse_date(data["join_date"])  # noqa: F841
    except Exception:
        return Response({"error": "join_date must be YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        monthly_salary = Decimal(str(data["monthly_salary"]))
    except Exception:
        return Response({"error": "monthly_salary must be a valid decimal"}, status=status.HTTP_400_BAD_REQUEST)

    # Extract and hash password if provided
    password = data.get("password")
    if password:
        # Hash the password using Django's default password hasher
        hashed_password = make_password(password)
        data["password_hash"] = hashed_password

    staff_input = {
        "business_id": business.business_id,  # SlugRelatedField expects slug
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "role": data["role"],
        "email": data.get("email"),
        "phone": data.get("phone"),
        "join_date": data["join_date"],
        "status": True,
    }

    # Add password hash if it was created
    if password and "password_hash" in data:
        staff_input["password_hash"] = data["password_hash"]

    serializer = BusinessStaffSerializer(data=staff_input)
    if not serializer.is_valid():
        return Response({"error": "Validation failed", "details": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    staff = serializer.save()

    # Create monthly payment record (no salary structure table needed)
    today = date.today()
    payment = BusinessStaffSalaryPayments.objects.create(
        staff_id=staff,
        business_id=business,
        year=today.year,
        month=today.month,
        salary_amount=monthly_salary,
        salary_paid=Decimal("0.00"),
        is_paid=False,
        remarks=None,
    )

    staff_payload = BusinessStaffSerializer(staff).data
    
    # Include password hash in response if it was set
    if password and "password_hash" in data:
        staff_payload["password_hash"] = data["password_hash"]
    
    salary_payload = {
        "payment_id": payment.payment_id,
        "year": payment.year,
        "month": payment.month,
        "salary_amount": str(payment.salary_amount),
        "salary_paid": str(payment.salary_paid),
        "is_paid": payment.is_paid,
    }

    return Response({"message": "Staff created", "staff": staff_payload, "salary": salary_payload}, status=status.HTTP_201_CREATED)


@swagger_auto_schema(methods=['GET'],tags=['management'])
@api_view(["GET"])
def get_staff_detail(request, staff_id: int):
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)
    
    staff = get_object_or_404(BusinessStaff, pk=staff_id, business_id=business)
    today = date.today()

    payment = (
        BusinessStaffSalaryPayments.objects.filter(
            staff_id=staff, business_id=staff.business_id, year=today.year, month=today.month
        ).first()
    )

    present = BusinessStaffAttendance.objects.filter(
        staff_id=staff,
        business_id=staff.business_id,
        attendance_date__year=today.year,
        attendance_date__month=today.month,
        attendance_status="Present",
    ).count()

    absent = BusinessStaffAttendance.objects.filter(
        staff_id=staff,
        business_id=staff.business_id,
        attendance_date__year=today.year,
        attendance_date__month=today.month,
        attendance_status="Absent",
    ).count()

    leave = BusinessStaffAttendance.objects.filter(
        staff_id=staff,
        business_id=staff.business_id,
        attendance_date__year=today.year,
        attendance_date__month=today.month,
        attendance_status="Leave",
    ).count()

    holiday = BusinessStaffAttendance.objects.filter(
        staff_id=staff,
        business_id=staff.business_id,
        attendance_date__year=today.year,
        attendance_date__month=today.month,
        attendance_status="Holiday",
    ).count()

    total_working_days = present + absent

    staff_payload = BusinessStaffSerializer(staff).data
    current_month = {
        "year": today.year,
        "month": today.month,
        "salary": {
            "salary_amount": str(payment.salary_amount) if payment else None,
            "salary_paid": str(payment.salary_paid) if payment else None,
            "is_paid": payment.is_paid if payment else False,
        },
        "attendance_summary": {
            "present": present,
            "absent": absent,
            "leave": leave,
            "holiday": holiday,
            "total_working_days": total_working_days,
        },
    }

    return Response({"staff": staff_payload, "current_month": current_month}, status=status.HTTP_200_OK)


def _get_staff_list(request, business):
    qs = BusinessStaff.objects.filter(business_id=business)

    role = request.GET.get("role")
    if role:
        qs = qs.filter(role=role)

    status_param = request.GET.get("status")
    if status_param is not None:
        val = str(status_param).lower()
        if val in {"1", "true", "yes"}:
            qs = qs.filter(status=True)
        elif val in {"0", "false", "no"}:
            qs = qs.filter(status=False)

    q = request.GET.get("q")
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
        )

    try:
        limit = int(request.GET.get("limit", 50))
        offset = int(request.GET.get("offset", 0))
    except ValueError:
        return Response({"error": "limit and offset must be integers"}, status=status.HTTP_400_BAD_REQUEST)

    total = qs.count()
    qs = qs.order_by("-created_at")[offset : offset + limit]
    
    # Get staff data with attendance information
    staff_list = []
    today = date.today()
    
    # Get year and month parameters for attendance data (default to current month)
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))
    
    for staff in qs:
        # Get basic staff data
        staff_data = BusinessStaffSerializer(staff).data
        
        # Get current month salary information
        current_payment = BusinessStaffSalaryPayments.objects.filter(
            staff_id=staff, business_id=business, year=year, month=month
        ).first()
        
        # Get attendance data for the specified month
        attendance_records = BusinessStaffAttendance.objects.filter(
            staff_id=staff,
            business_id=business,
            attendance_date__year=year,
            attendance_date__month=month
        ).order_by('attendance_date')
        
        # Count attendance by status
        present_count = attendance_records.filter(attendance_status="Present").count()
        absent_count = attendance_records.filter(attendance_status="Absent").count()
        leave_count = attendance_records.filter(attendance_status="Leave").count()
        holiday_count = attendance_records.filter(attendance_status="Holiday").count()
        
        # Get detailed attendance with dates
        present_dates = list(attendance_records.filter(attendance_status="Present").values_list('attendance_date', flat=True))
        absent_dates = list(attendance_records.filter(attendance_status="Absent").values_list('attendance_date', flat=True))
        leave_dates = list(attendance_records.filter(attendance_status="Leave").values_list('attendance_date', flat=True))
        holiday_dates = list(attendance_records.filter(attendance_status="Holiday").values_list('attendance_date', flat=True))
        
        # Convert dates to ISO format strings
        present_dates = [d.isoformat() for d in present_dates]
        absent_dates = [d.isoformat() for d in absent_dates]
        leave_dates = [d.isoformat() for d in leave_dates]
        holiday_dates = [d.isoformat() for d in holiday_dates]
        
        total_working_days = present_count + absent_count
        
        # Calculate salary information if payment record exists
        if current_payment:
            monthly_salary = current_payment.salary_amount
            daily_rate = monthly_salary / Decimal(total_working_days) if total_working_days > 0 else Decimal("0.00")
            calculated_salary = daily_rate * Decimal(present_count) if total_working_days > 0 else Decimal("0.00")
            
            current_salary = {
                "base_salary_amount": str(monthly_salary),
                "calculated_salary_amount": str(calculated_salary.quantize(Decimal("0.01"))),
                "daily_rate": str(daily_rate.quantize(Decimal("0.01"))),
                "present_days": present_count,
                "working_days_in_month": total_working_days,
                "half_days": 0,  # You can implement half-day logic if needed
                "calculation_month": f"{year}-{month:02d}",
                "is_paid": current_payment.is_paid,
                "salary_paid": str(current_payment.salary_paid)
            }
        else:
            current_salary = None
        
        # Add attendance information to staff data
        staff_data['current_salary'] = current_salary
        staff_data['attendance_summary'] = {
            "year": year,
            "month": month,
            "present_count": present_count,
            "absent_count": absent_count,
            "leave_count": leave_count,
            "holiday_count": holiday_count,
            "total_working_days": total_working_days
        }
        staff_data['attendance_details'] = {
            "present_dates": present_dates,
            "absent_dates": absent_dates,
            "leave_dates": leave_dates,
            "holiday_dates": holiday_dates
        }
        
        staff_list.append(staff_data)

    return Response({
        "results": staff_list, 
        "count": total, 
        "limit": limit, 
        "offset": offset,
        "attendance_period": {
            "year": year,
            "month": month,
            "month_name": date(year, month, 1).strftime("%B %Y")
        }
    }, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['GET'],tags=['management'])
@api_view(["GET"])
def debug_salary_records(request):
    """Debug endpoint to check salary records"""
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get all staff and their salary records
    staff_members = BusinessStaff.objects.filter(business_id=business)
    debug_info = []
    
    for staff in staff_members:
        payment_records = BusinessStaffSalaryPayments.objects.filter(staff_id=staff)
        
        debug_info.append({
            "staff_id": staff.staff_id,
            "staff_name": staff.full_name,
            "status": staff.status,
            "join_date": staff.join_date.strftime('%Y-%m-%d') if staff.join_date else None,
            "payment_records_count": payment_records.count(),
            "payment_records": [
                {
                    "payment_id": pr.payment_id,
                    "year": pr.year,
                    "month": pr.month,
                    "amount": str(pr.salary_amount),
                    "paid": str(pr.salary_paid),
                    "is_paid": pr.is_paid,
                    "remarks": pr.remarks
                } for pr in payment_records
            ]
        })
    
    return Response({"debug_info": debug_info}, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['GET'],tags=['management'])
@api_view(["GET"])
def test_payment_creation(request):
    """Test endpoint to manually create and test payment records"""
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)
    
    results = []
    today = date.today()
    
    # Get all staff
    staff_members = BusinessStaff.objects.filter(business_id=business)
    
    for staff in staff_members:
        # Delete existing payment records for current month
        deleted_count = BusinessStaffSalaryPayments.objects.filter(
            staff_id=staff, 
            year=today.year, 
            month=today.month
        ).count()
        BusinessStaffSalaryPayments.objects.filter(
            staff_id=staff, 
            year=today.year, 
            month=today.month
        ).delete()
        
        # Create new payment record
        payment_record = BusinessStaffSalaryPayments.objects.create(
            staff_id=staff,
            business_id=business,
            year=today.year,
            month=today.month,
            salary_amount=Decimal("35000.00"),
            salary_paid=Decimal("0.00"),
            is_paid=False,
            remarks="Test payment record"
        )
        
        # Test direct query
        direct_query = BusinessStaffSalaryPayments.objects.filter(staff_id=staff)
        
        results.append({
            "staff_id": staff.staff_id,
            "staff_name": staff.full_name,
            "deleted_records": deleted_count,
            "created_payment_id": payment_record.payment_id,
            "created_amount": str(payment_record.salary_amount),
            "direct_query_count": direct_query.count(),
            "test_successful": direct_query.count() > 0
        })
    
    return Response({"test_results": results}, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['POST'],tags=['management'])
@api_view(["POST"])
@transaction.atomic
def mark_attendance(request):
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    user_id = request.GET.get("user_id")
    if not user_id:
        return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)

    # Get the user who is marking attendance (from Registration model)
    try:
        marker_user = Registration.objects.get(user_id=user_id)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid user_id"}, status=status.HTTP_400_BAD_REQUEST)

    data = request.data
    required = [
        "staff_id",
        "attendance_date",
        "attendance_status",
    ]
    missing = [k for k in required if data.get(k) in (None, "")]
    if missing:
        return Response({"error": f"Missing fields: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST)

    status_allowed = {"Present", "Absent", "Leave", "Holiday"}
    if data.get("attendance_status") not in status_allowed:
        return Response({"error": "attendance_status must be one of Present, Absent, Leave, Holiday"}, status=status.HTTP_400_BAD_REQUEST)

    staff = get_object_or_404(BusinessStaff, pk=data["staff_id"], business_id=business)

    # Check if this user has permission to mark attendance for this business
    # You can add additional business-user relationship validation here if needed
    # For now, we'll allow any registered user to mark attendance

    try:
        att_date = _parse_date(data["attendance_date"])  # noqa: F841
    except Exception:
        return Response({"error": "attendance_date must be YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

    check_in = data.get("check_in")
    check_out = data.get("check_out")
    
    # Append user_id info to remarks to preserve it in database
    original_remarks = data.get("remarks", "")
    enhanced_remarks = f"[Marked by user_id: {marker_user.user_id} - {marker_user.firstName} {marker_user.lastName}]"
    if original_remarks:
        enhanced_remarks = f"{original_remarks} {enhanced_remarks}"

    if check_in:
        try:
            _parse_time(check_in)
        except Exception:
            return Response({"error": "check_in must be HH:MM:SS"}, status=status.HTTP_400_BAD_REQUEST)

    if check_out:
        try:
            _parse_time(check_out)
        except Exception:
            return Response({"error": "check_out must be HH:MM:SS"}, status=status.HTTP_400_BAD_REQUEST)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT attendance_id FROM business_staff_attendance
            WHERE staff_id = %s AND business_id = %s AND attendance_date = %s
            """,
            [staff.staff_id, business.business_id, data["attendance_date"]],
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE business_staff_attendance
                SET attendance_status = %s,
                    marked_by = %s,
                    check_in = %s,
                    check_out = %s,
                    remarks = %s,
                    updated_at = CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                WHERE attendance_id = %s
                """,
                [
                    data["attendance_status"],
                    None,  # Set marked_by as NULL due to foreign key constraint
                    check_in,
                    check_out,
                    enhanced_remarks,  # Use enhanced remarks with user info
                    existing[0],
                ],
            )
            attendance_id = existing[0]
        else:
            cursor.execute(
                """
                INSERT INTO business_staff_attendance (
                    staff_id, business_id, attendance_date, attendance_status, marked_by, check_in, check_out, remarks, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata'), CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                )
                """,
                [
                    staff.staff_id,
                    business.business_id,
                    data["attendance_date"],
                    data["attendance_status"],
                    None,  # Set marked_by as NULL due to foreign key constraint
                    check_in,
                    check_out,
                    enhanced_remarks,  # Use enhanced remarks with user info
                ],
            )
            attendance_id = cursor.lastrowid

        cursor.execute(
            """
            SELECT attendance_id, staff_id, business_id, attendance_date, attendance_status, marked_by, check_in, check_out, working_hours, remarks, created_at, updated_at
            FROM business_staff_attendance
            WHERE attendance_id = %s
            """,
            [attendance_id],
        )
        row = cursor.fetchone()

    payload = {
        "attendance_id": row[0],
        "staff_id": row[1],
        "business_id": row[2],
        "attendance_date": row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3]),
        "attendance_status": row[4],
        "marked_by": row[5],  # This will be NULL due to foreign key constraint
        "marked_by_user_id": marker_user.user_id,  # Add the actual user_id who marked
        "marked_by_user_name": f"{marker_user.firstName} {marker_user.lastName}",
        "check_in": row[6].strftime("%H:%M:%S") if row[6] else None,
        "check_out": row[7].strftime("%H:%M:%S") if row[7] else None,
        "working_hours": float(row[8]) if row[8] is not None else None,
        "remarks": row[9],
        "created_at": row[10].isoformat() if hasattr(row[10], "isoformat") else str(row[10]),
        "updated_at": row[11].isoformat() if hasattr(row[11], "isoformat") else str(row[11]),
    }

    return Response({"message": "Attendance recorded", "attendance": payload}, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['GET'], tags=['management'])
@api_view(["GET"])
def get_staff_salary(request, staff_id: int):
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)

    year = request.GET.get("year")
    month = request.GET.get("month")
    if not year or not month:
        return Response({"error": "year and month are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        year = int(year)
        month = int(month)
        if month < 1 or month > 12:
            raise ValueError
    except Exception:
        return Response({"error": "year must be int, month must be 1-12"}, status=status.HTTP_400_BAD_REQUEST)

    staff = get_object_or_404(BusinessStaff, pk=staff_id, business_id=business)

    payment = BusinessStaffSalaryPayments.objects.filter(
        staff_id=staff, business_id=staff.business_id, year=year, month=month
    ).first()

    # Get attendance breakdown
    present = BusinessStaffAttendance.objects.filter(
        staff_id=staff,
        business_id=staff.business_id,
        attendance_date__year=year,
        attendance_date__month=month,
        attendance_status="Present",
    ).count()

    absent = BusinessStaffAttendance.objects.filter(
        staff_id=staff,
        business_id=staff.business_id,
        attendance_date__year=year,
        attendance_date__month=month,
        attendance_status="Absent",
    ).count()

    leave = BusinessStaffAttendance.objects.filter(
        staff_id=staff,
        business_id=staff.business_id,
        attendance_date__year=year,
        attendance_date__month=month,
        attendance_status="Leave",
    ).count()

    holiday = BusinessStaffAttendance.objects.filter(
        staff_id=staff,
        business_id=staff.business_id,
        attendance_date__year=year,
        attendance_date__month=month,
        attendance_status="Holiday",
    ).count()

    total_working_days = present + absent
    total_days_marked = present + absent + leave + holiday

    # Calculate salary based on present days
    monthly_salary = Decimal(str(payment.salary_amount)) if payment else Decimal("0.00")
    
    # Calculate payable salary: (monthly_salary / total_working_days) * present_days
    if total_working_days > 0:
        daily_salary = monthly_salary / Decimal(total_working_days)
        payable_salary = daily_salary * Decimal(present)
        salary_deduction = daily_salary * Decimal(absent)
    else:
        daily_salary = Decimal("0.00")
        payable_salary = Decimal("0.00")
        salary_deduction = Decimal("0.00")

    # Check if salary record exists for the month
    salary_created = payment is not None

    payload = {
        "staff_info": {
            "staff_id": staff.staff_id,
            "staff_name": staff.full_name,
            "role": staff.role,
            "email": staff.email,
            "phone": staff.phone,
            "join_date": staff.join_date.isoformat() if staff.join_date else None,
            "status": staff.status
        },
        "business_info": {
            "business_id": staff.business_id.business_id,
            "business_name": staff.business_id.business_name if hasattr(staff.business_id, 'business_name') else None
        },
        "salary_period": {
            "year": year,
            "month": month,
            "month_name": date(year, month, 1).strftime("%B %Y")
        },
        "attendance_summary": {
            "present_days": present,
            "absent_days": absent,
            "leave_days": leave,
            "holiday_days": holiday,
            "total_working_days": total_working_days,
            "total_days_marked": total_days_marked
        },
        "salary_details": {
            "monthly_salary": str(monthly_salary),
            "daily_salary": str(daily_salary.quantize(Decimal("0.01"))),
            "payable_salary": str(payable_salary.quantize(Decimal("0.01"))),
            "salary_deduction": str(salary_deduction.quantize(Decimal("0.01"))),
            "salary_paid": str(payment.salary_paid) if payment else "0.00",
            "remaining_salary": str((payable_salary - (payment.salary_paid if payment else Decimal("0.00"))).quantize(Decimal("0.01"))),
            "is_paid": payment.is_paid if payment else False,
            "salary_record_created": salary_created
        }
    }

    return Response(payload, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['GET'],tags=['management'])
@api_view(["GET"])
def get_all_staff_salaries(request):
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)

    year = request.GET.get("year")
    month = request.GET.get("month")
    if not year or not month:
        return Response({"error": "year and month are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        year = int(year)
        month = int(month)
        if month < 1 or month > 12:
            raise ValueError
    except Exception:
        return Response({"error": "year must be int, month must be 1-12"}, status=status.HTTP_400_BAD_REQUEST)

    # Get all staff for this business
    staff_list = BusinessStaff.objects.filter(business_id=business)
    
    staff_salaries = []
    
    for staff in staff_list:
        payment = BusinessStaffSalaryPayments.objects.filter(
            staff_id=staff, business_id=staff.business_id, year=year, month=month
        ).first()

        # Get attendance breakdown
        present = BusinessStaffAttendance.objects.filter(
            staff_id=staff,
            business_id=staff.business_id,
            attendance_date__year=year,
            attendance_date__month=month,
            attendance_status="Present",
        ).count()

        absent = BusinessStaffAttendance.objects.filter(
            staff_id=staff,
            business_id=staff.business_id,
            attendance_date__year=year,
            attendance_date__month=month,
            attendance_status="Absent",
        ).count()

        leave = BusinessStaffAttendance.objects.filter(
            staff_id=staff,
            business_id=staff.business_id,
            attendance_date__year=year,
            attendance_date__month=month,
            attendance_status="Leave",
        ).count()

        holiday = BusinessStaffAttendance.objects.filter(
            staff_id=staff,
            business_id=staff.business_id,
            attendance_date__year=year,
            attendance_date__month=month,
            attendance_status="Holiday",
        ).count()

        total_working_days = present + absent
        total_days_marked = present + absent + leave + holiday

        # Calculate salary based on present days
        monthly_salary = Decimal(str(payment.salary_amount)) if payment else Decimal("0.00")
        
        # Calculate payable salary: (monthly_salary / total_working_days) * present_days
        if total_working_days > 0:
            daily_salary = monthly_salary / Decimal(total_working_days)
            payable_salary = daily_salary * Decimal(present)
            salary_deduction = daily_salary * Decimal(absent)
        else:
            daily_salary = Decimal("0.00")
            payable_salary = Decimal("0.00")
            salary_deduction = Decimal("0.00")

        # Check if salary record exists for the month
        salary_created = payment is not None

        staff_salary_data = {
            "staff_info": {
                "staff_id": staff.staff_id,
                "staff_name": staff.full_name,
                "role": staff.role,
                "email": staff.email,
                "phone": staff.phone,
                "join_date": staff.join_date.isoformat() if staff.join_date else None,
                "status": staff.status
            },
            "attendance_summary": {
                "present_days": present,
                "absent_days": absent,
                "leave_days": leave,
                "holiday_days": holiday,
                "total_working_days": total_working_days,
                "total_days_marked": total_days_marked
            },
            "salary_details": {
                "monthly_salary": str(monthly_salary),
                "daily_salary": str(daily_salary.quantize(Decimal("0.01"))),
                "payable_salary": str(payable_salary.quantize(Decimal("0.01"))),
                "salary_deduction": str(salary_deduction.quantize(Decimal("0.01"))),
                "salary_paid": str(payment.salary_paid) if payment else "0.00",
                "remaining_salary": str((payable_salary - (payment.salary_paid if payment else Decimal("0.00"))).quantize(Decimal("0.01"))),
                "is_paid": payment.is_paid if payment else False,
                "salary_record_created": salary_created
            }
        }
        
        staff_salaries.append(staff_salary_data)

    # Calculate totals
    total_staff = len(staff_salaries)
    total_monthly_salary = sum((Decimal(s["salary_details"]["monthly_salary"]) for s in staff_salaries), Decimal("0.00"))
    total_payable_salary = sum((Decimal(s["salary_details"]["payable_salary"]) for s in staff_salaries), Decimal("0.00"))
    total_salary_paid = sum((Decimal(s["salary_details"]["salary_paid"]) for s in staff_salaries), Decimal("0.00"))
    total_remaining_salary = sum((Decimal(s["salary_details"]["remaining_salary"]) for s in staff_salaries), Decimal("0.00"))

    payload = {
        "business_info": {
            "business_id": business.business_id,
            "business_name": business.business_name if hasattr(business, 'business_name') else None
        },
        "salary_period": {
            "year": year,
            "month": month,
            "month_name": date(year, month, 1).strftime("%B %Y")
        },
        "summary": {
            "total_staff": total_staff,
            "total_monthly_salary": str(total_monthly_salary.quantize(Decimal("0.01"))),
            "total_payable_salary": str(total_payable_salary.quantize(Decimal("0.01"))),
            "total_salary_paid": str(total_salary_paid.quantize(Decimal("0.01"))),
            "total_remaining_salary": str(total_remaining_salary.quantize(Decimal("0.01")))
        },
        "staff_salaries": staff_salaries
    }

    return Response(payload, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['PUT'],tags=['management'])
@api_view(["PUT"])
def update_staff(request, staff_id):
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        staff = BusinessStaff.objects.get(staff_id=staff_id, business_id=business)
    except BusinessStaff.DoesNotExist:
        return Response({"error": "Staff not found"}, status=status.HTTP_404_NOT_FOUND)

    data = request.data
    
    # Update staff fields
    if 'first_name' in data:
        staff.first_name = data['first_name']
    if 'last_name' in data:
        staff.last_name = data['last_name']
    if 'role' in data:
        staff.role = data['role']
    if 'email' in data:
        staff.email = data['email']
    if 'phone' in data:
        staff.phone = data['phone']
    if 'hire_date' in data:
        staff.join_date = data['hire_date']
    
    staff.save()
    
    # Serialize the updated staff
    serializer = BusinessStaffSerializer(staff)
    
    return Response({
        "message": "Staff updated successfully",
        "staff": serializer.data
    }, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['DELETE'],tags=['management'])
@api_view(["DELETE"])
def delete_staff(request, staff_id):
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    hard_delete = request.GET.get("hard_delete", "false").lower() == "true"

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        staff = BusinessStaff.objects.get(staff_id=staff_id, business_id=business)
    except BusinessStaff.DoesNotExist:
        return Response({"error": "Staff not found"}, status=status.HTTP_404_NOT_FOUND)

    if hard_delete:
        # Check if staff has salary records
        has_salary_records = BusinessStaffSalaryPayments.objects.filter(staff_id=staff).exists()
        if has_salary_records:
            return Response({
                "error": "Cannot hard delete staff with existing salary records. Use soft delete instead."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        staff.delete()
        message = "Staff permanently deleted"
    else:
        # Soft delete - just set status to False
        staff.status = False
        staff.save()
        message = "Staff deactivated"

    return Response({"message": message}, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['GET'],tags=['management'])
@api_view(["GET"])
def get_staff_attendance(request, staff_id: int):
    """Get detailed attendance data for a specific staff member"""
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)

    staff = get_object_or_404(BusinessStaff, pk=staff_id, business_id=business)
    
    # Get year and month parameters (default to current month)
    today = date.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))
    
    # Validate month
    if month < 1 or month > 12:
        return Response({"error": "month must be between 1 and 12"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get all attendance records for the specified month
    attendance_records = BusinessStaffAttendance.objects.filter(
        staff_id=staff,
        business_id=business,
        attendance_date__year=year,
        attendance_date__month=month
    ).order_by('attendance_date')
    
    # Group attendance by status with dates and details
    attendance_by_status = {
        "Present": [],
        "Absent": [],
        "Leave": [],
        "Holiday": []
    }
    
    for record in attendance_records:
        attendance_info = {
            "date": record.attendance_date.isoformat(),
            "check_in": record.check_in.strftime("%H:%M:%S") if record.check_in else None,
            "check_out": record.check_out.strftime("%H:%M:%S") if record.check_out else None,
            "working_hours": float(record.working_hours) if record.working_hours else None,
            "remarks": record.remarks
        }
        
        if record.attendance_status in attendance_by_status:
            attendance_by_status[record.attendance_status].append(attendance_info)
    
    # Count totals
    present_count = len(attendance_by_status["Present"])
    absent_count = len(attendance_by_status["Absent"])
    leave_count = len(attendance_by_status["Leave"])
    holiday_count = len(attendance_by_status["Holiday"])
    total_working_days = present_count + absent_count
    
    # Get salary information for the month
    payment = BusinessStaffSalaryPayments.objects.filter(
        staff_id=staff, business_id=business, year=year, month=month
    ).first()
    
    salary_info = None
    if payment:
        monthly_salary = payment.salary_amount
        daily_rate = monthly_salary / Decimal(total_working_days) if total_working_days > 0 else Decimal("0.00")
        calculated_salary = daily_rate * Decimal(present_count) if total_working_days > 0 else Decimal("0.00")
        
        salary_info = {
            "monthly_salary": str(monthly_salary),
            "daily_rate": str(daily_rate.quantize(Decimal("0.01"))),
            "calculated_salary": str(calculated_salary.quantize(Decimal("0.01"))),
            "salary_paid": str(payment.salary_paid),
            "is_paid": payment.is_paid
        }
    
    payload = {
        "staff_info": {
            "staff_id": staff.staff_id,
            "staff_name": staff.full_name,
            "role": staff.role,
            "email": staff.email,
            "phone": staff.phone,
            "join_date": staff.join_date.isoformat() if staff.join_date else None,
            "status": staff.status
        },
        "attendance_period": {
            "year": year,
            "month": month,
            "month_name": date(year, month, 1).strftime("%B %Y")
        },
        "attendance_summary": {
            "present_count": present_count,
            "absent_count": absent_count,
            "leave_count": leave_count,
            "holiday_count": holiday_count,
            "total_working_days": total_working_days,
            "total_days_marked": present_count + absent_count + leave_count + holiday_count
        },
        "attendance_details": attendance_by_status,
        "salary_info": salary_info
    }
    
    return Response(payload, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['POST'],tags=['management'])
@api_view(["POST"])
@transaction.atomic
def pay_staff_salary(request, staff_id: int):
    """Pay salary to a specific staff member"""
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)

    # Get the staff member
    staff = get_object_or_404(BusinessStaff, pk=staff_id, business_id=business)
    
    # Get required fields from request
    year = request.data.get("year")
    month = request.data.get("month")
    payment_amount = request.data.get("payment_amount")
    remarks = request.data.get("remarks", "")
    
    # Validate required fields
    if not year or not month or not payment_amount:
        return Response({
            "error": "year, month, and payment_amount are required"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        year = int(year)
        month = int(month)
        payment_amount = Decimal(str(payment_amount))
    except (ValueError, TypeError):
        return Response({
            "error": "Invalid year, month, or payment_amount format"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate month
    if month < 1 or month > 12:
        return Response({"error": "month must be between 1 and 12"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate payment amount
    if payment_amount <= 0:
        return Response({"error": "payment_amount must be greater than 0"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get or create salary payment record
    try:
        salary_payment = BusinessStaffSalaryPayments.objects.get(
            staff_id=staff,
            business_id=business,
            year=year,
            month=month
        )
        
        # Check if already fully paid
        if salary_payment.is_paid and salary_payment.salary_paid >= salary_payment.salary_amount:
            return Response({
                "error": "Salary for this month is already fully paid",
                "current_payment": {
                    "salary_amount": str(salary_payment.salary_amount),
                    "salary_paid": str(salary_payment.salary_paid),
                    "remaining_amount": str(salary_payment.salary_amount - salary_payment.salary_paid),
                    "is_paid": salary_payment.is_paid
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate new payment amount
        new_total_paid = salary_payment.salary_paid + payment_amount
        
        # Check if payment exceeds salary amount
        if new_total_paid > salary_payment.salary_amount:
            return Response({
                "error": f"Payment amount exceeds remaining salary. Maximum payable: {salary_payment.salary_amount - salary_payment.salary_paid}",
                "current_payment": {
                    "salary_amount": str(salary_payment.salary_amount),
                    "salary_paid": str(salary_payment.salary_paid),
                    "remaining_amount": str(salary_payment.salary_amount - salary_payment.salary_paid),
                    "requested_amount": str(payment_amount)
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update payment record
        old_paid_amount = salary_payment.salary_paid
        salary_payment.salary_paid = new_total_paid
        salary_payment.is_paid = (new_total_paid >= salary_payment.salary_amount)
        if remarks:
            salary_payment.remarks = remarks
        salary_payment.save()
        
        action_type = "partial_payment" if not salary_payment.is_paid else "full_payment"
        
    except BusinessStaffSalaryPayments.DoesNotExist:
        return Response({
            "error": "No salary record found for this staff member for the specified month. Please create salary record first."
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Prepare response
    month_name = date(year, month, 1).strftime("%B %Y")
    
    response_data = {
        "message": f"Salary payment successful for {staff.full_name}",
        "payment_details": {
            "staff_info": {
                "staff_id": staff.staff_id,
                "staff_name": staff.full_name,
                "role": staff.role,
                "email": staff.email,
                "phone": staff.phone
            },
            "payment_period": {
                "year": year,
                "month": month,
                "month_name": month_name
            },
            "payment_summary": {
                "total_salary_amount": str(salary_payment.salary_amount),
                "previous_paid_amount": str(old_paid_amount),
                "current_payment_amount": str(payment_amount),
                "total_paid_amount": str(salary_payment.salary_paid),
                "remaining_amount": str(salary_payment.salary_amount - salary_payment.salary_paid),
                "is_fully_paid": salary_payment.is_paid,
                "payment_status": "Fully Paid" if salary_payment.is_paid else "Partially Paid"
            },
            "payment_action": action_type,
            "remarks": salary_payment.remarks or "",
            "payment_date": salary_payment.updated_at.isoformat()
        }
    }
    
    return Response(response_data, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['GET'],tags=['management'])
@api_view(["GET"])
def get_staff_salary_payment_status(request, staff_id: int):
    """Get salary payment status for a specific staff member"""
    business_id = request.GET.get("business_id")
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_400_BAD_REQUEST)

    # Get the staff member
    staff = get_object_or_404(BusinessStaff, pk=staff_id, business_id=business)
    
    # Get year and month parameters (default to current month)
    today = date.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))
    
    # Validate month
    if month < 1 or month > 12:
        return Response({"error": "month must be between 1 and 12"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        salary_payment = BusinessStaffSalaryPayments.objects.get(
            staff_id=staff,
            business_id=business,
            year=year,
            month=month
        )
        
        month_name = date(year, month, 1).strftime("%B %Y")
        
        response_data = {
            "staff_info": {
                "staff_id": staff.staff_id,
                "staff_name": staff.full_name,
                "role": staff.role,
                "email": staff.email,
                "phone": staff.phone,
                "status": staff.status
            },
            "payment_period": {
                "year": year,
                "month": month,
                "month_name": month_name
            },
            "salary_details": {
                "total_salary_amount": str(salary_payment.salary_amount),
                "total_paid_amount": str(salary_payment.salary_paid),
                "remaining_amount": str(salary_payment.salary_amount - salary_payment.salary_paid),
                "is_fully_paid": salary_payment.is_paid,
                "payment_status": "Fully Paid" if salary_payment.is_paid else "Partially Paid" if salary_payment.salary_paid > 0 else "Not Paid",
                "payment_percentage": float((salary_payment.salary_paid / salary_payment.salary_amount * 100).quantize(Decimal("0.01"))) if salary_payment.salary_amount > 0 else 0,
                "remarks": salary_payment.remarks or ""
            },
            "payment_history": {
                "created_at": salary_payment.created_at.isoformat(),
                "last_updated": salary_payment.updated_at.isoformat()
            }
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except BusinessStaffSalaryPayments.DoesNotExist:
        return Response({
            "error": "No salary record found for this staff member for the specified month",
            "staff_info": {
                "staff_id": staff.staff_id,
                "staff_name": staff.full_name,
                "role": staff.role
            },
            "requested_period": {
                "year": year,
                "month": month,
                "month_name": date(year, month, 1).strftime("%B %Y")
            }
        }, status=status.HTTP_404_NOT_FOUND)


# ==================== Staff Authentication Views ====================

class StaffLoginView(APIView):
    """Handle staff login with password or OTP"""
    permission_classes = [AllowAny]

    def post(self, request):
        """Login staff member"""
        try:
            serializer = StaffLoginSerializer(data=request.data)
            if serializer.is_valid():
                login_data = serializer.create(serializer.validated_data)
                
                # Log successful login
                self._create_login_log(
                    staff_id=login_data['staff_id'],
                    business_id=login_data['business_id'],
                    login_method=login_data['login_method'],
                    login_status='SUCCESS',
                    request=request
                )
                
                return Response({
                    'success': True,
                    'message': 'Login successful',
                    'data': login_data
                }, status=status.HTTP_200_OK)
            
            return Response({
                'success': False,
                'message': 'Login failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Staff login error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _create_login_log(self, staff_id, business_id, login_method, login_status, request, failure_reason=None):
        """Create login log entry for password-based login"""
        try:
            ip_address = self._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')

            StaffLoginLogs.objects.create(
                staff_id_id=staff_id,
                business_id_id=business_id,
                login_method=login_method,
                login_status=login_status,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason=failure_reason
            )
        except Exception as e:
            logger.error(f"Failed to create login log: {str(e)}")

    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class StaffChangePasswordView(APIView):
    """Allow staff to change their password (plain-text per requirement)"""
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            serializer = StaffChangePasswordSerializer(data=request.data)
            if serializer.is_valid():
                result = serializer.create(serializer.validated_data)
                return Response({'success': True, **result}, status=status.HTTP_200_OK)

            return Response({
                'success': False,
                'message': 'Password change failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Staff change password error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StaffLoginLogsView(APIView):
    """Get staff login logs"""
    
    def get(self, request):
        """Get login logs for a staff member"""
        try:
            staff_id = request.query_params.get('staff_id')
            business_id = request.query_params.get('business_id')
            
            if not staff_id or not business_id:
                return Response({
                    'success': False,
                    'message': 'Staff ID and Business ID are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logs = StaffLoginLogs.objects.filter(
                staff_id_id=staff_id,
                business_id_id=business_id
            ).order_by('-login_time')
            
            serializer = StaffLoginLogsSerializer(logs, many=True)
            return Response({'success': True, 'data': serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Staff login logs error: {str(e)}")
            return Response({'success': False, 'message': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StaffNavAssignmentView(APIView):
    """CRUD for assigning navigation items to a specific staff member"""

    def get(self, request, staff_id: int):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({'success': False, 'message': 'Business ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, business_id=business_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({'success': False, 'message': 'Staff not found'}, status=status.HTTP_404_NOT_FOUND)

        assigned_ids = staff.nav_items or []

        # Build hierarchical details
        navigation_items = []
        if assigned_ids:
            parents = RoleBasedNavItems.objects.filter(
                Q(id__in=assigned_ids) & Q(parent__isnull=True),
                status=True,
                is_visible=True
            ).order_by('order_index')

            for parent in parents:
                item = {
                    'id': parent.id,
                    'nav_name': parent.nav_name,
                    'sub_nav': parent.sub_nav,
                    'icon': parent.icon,
                    'route_path': parent.route_path,
                    'order_index': parent.order_index,
                    'children': []
                }
                children = RoleBasedNavItems.objects.filter(
                    parent_id=parent.id,
                    id__in=assigned_ids,
                    status=True,
                    is_visible=True
                ).order_by('order_index')
                for child in children:
                    item['children'].append({
                        'id': child.id,
                        'nav_name': child.nav_name,
                        'sub_nav': child.sub_nav,
                        'icon': child.icon,
                        'route_path': child.route_path,
                        'order_index': child.order_index
                    })
                navigation_items.append(item)

        return Response({
            'success': True,
            'data': {
                'staff_id': staff.staff_id,
                'business_id': staff.business_id.business_id,
                'staff_name': staff.full_name,
                'role': staff.role,
                'email': staff.email,
                'mobile_number': staff.mobile_number or staff.phone,
                'phone': staff.phone,
                'last_login': staff.last_login,
                'status': staff.status,
                'assigned_ids': assigned_ids,
                'navigation_items': navigation_items
            }
        }, status=status.HTTP_200_OK)

    def put(self, request, staff_id: int):
        """Replace the entire assignment with provided list of IDs"""
        return self._set_assignment(request, staff_id, replace=True)

    def post(self, request, staff_id: int):
        """Add provided IDs to existing assignment (union)"""
        return self._set_assignment(request, staff_id, replace=False)

    def delete(self, request, staff_id: int):
        """Remove provided IDs from assignment or clear all if none provided"""
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({'success': False, 'message': 'Business ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, business_id=business_id)
        except BusinessStaff.DoesNotExist:
            return Response({'success': False, 'message': 'Staff not found'}, status=status.HTTP_404_NOT_FOUND)

        ids = request.data.get('nav_item_ids')
        if ids is None:
            staff.nav_items = []
        else:
            current = set(staff.nav_items or [])
            to_remove = set(int(i) for i in ids)
            staff.nav_items = list(current - to_remove)
        staff.save(update_fields=['nav_items'])
        return Response({'success': True, 'message': 'Assignment updated', 'assigned_ids': staff.nav_items}, status=status.HTTP_200_OK)

    def _set_assignment(self, request, staff_id: int, replace: bool):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({'success': False, 'message': 'Business ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        ids = request.data.get('nav_item_ids')
        if not isinstance(ids, list) or not all(str(i).isdigit() for i in ids):
            return Response({'success': False, 'message': 'nav_item_ids must be a list of integers'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate all IDs exist
        valid_ids = list(RoleBasedNavItems.objects.filter(id__in=ids, status=True, is_visible=True).values_list('id', flat=True))
        if len(valid_ids) != len(set(ids)):
            return Response({'success': False, 'message': 'One or more nav_item_ids are invalid'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, business_id=business_id)
        except BusinessStaff.DoesNotExist:
            return Response({'success': False, 'message': 'Staff not found'}, status=status.HTTP_404_NOT_FOUND)

        if replace:
            staff.nav_items = list(sorted(set(int(i) for i in ids)))
        else:
            current = set(staff.nav_items or [])
            staff.nav_items = list(sorted(current.union(set(int(i) for i in ids))))

        staff.save(update_fields=['nav_items'])
        return Response({'success': True, 'message': 'Assignment saved', 'assigned_ids': staff.nav_items}, status=status.HTTP_200_OK)

class AllRoleNavItemsView(APIView):
    """List all navigation items hierarchically for assignment UI"""

    def get(self, request):
        parents = RoleBasedNavItems.objects.filter(parent__isnull=True, status=True, is_visible=True).order_by('order_index')
        data = []
        for p in parents:
            node = {
                'id': p.id,
                'nav_name': p.nav_name,
                'icon': p.icon,
                'route_path': p.route_path,
                'order_index': p.order_index,
                'sub_nav': []
            }
            children = RoleBasedNavItems.objects.filter(parent_id=p.id, status=True, is_visible=True).order_by('order_index')
            for c in children:
                node['sub_nav'].append({
                    'id': c.id,
                    'nav_name': c.nav_name,
                    'icon': c.icon,
                    'route_path': c.route_path,
                    'order_index': c.order_index
                })
            data.append(node)
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)

    def _create_login_log(self, staff_id, business_id, login_method, login_status, request, failure_reason=None):
        """Create login log entry"""
        try:
            ip_address = self._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            StaffLoginLogs.objects.create(
                staff_id_id=staff_id,
                business_id_id=business_id,
                login_method=login_method,
                login_status=login_status,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason=failure_reason
            )
        except Exception as e:
            logger.error(f"Failed to create login log: {str(e)}")

    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class StaffOTPSendView(APIView):
    """Send OTP to staff for login"""
    permission_classes = [AllowAny]

    def post(self, request):
        """Send OTP to staff member"""
        try:
            serializer = StaffOTPSendSerializer(data=request.data)
            if serializer.is_valid():
                otp_data = serializer.create(serializer.validated_data)
                
                return Response({
                    'success': True,
                    'message': 'OTP sent successfully',
                    'data': otp_data
                }, status=status.HTTP_200_OK)
            
            return Response({
                'success': False,
                'message': 'Failed to send OTP',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"OTP send error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StaffOTPVerifyView(APIView):
    """Verify OTP and login staff"""
    permission_classes = [AllowAny]

    def post(self, request):
        """Verify OTP and complete login"""
        try:
            serializer = StaffOTPVerifySerializer(data=request.data)
            if serializer.is_valid():
                login_data = serializer.create(serializer.validated_data)
                
                # Log successful login
                self._create_login_log(
                    staff_id=login_data['staff_id'],
                    business_id=login_data['business_id'],
                    login_method='OTP',
                    login_status='SUCCESS',
                    request=request
                )
                
                return Response({
                    'success': True,
                    'message': 'OTP verified successfully',
                    'data': login_data
                }, status=status.HTTP_200_OK)
            
            return Response({
                'success': False,
                'message': 'OTP verification failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"OTP verify error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _create_login_log(self, staff_id, business_id, login_method, login_status, request, failure_reason=None):
        """Create login log entry"""
        try:
            ip_address = self._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            StaffLoginLogs.objects.create(
                staff_id_id=staff_id,
                business_id_id=business_id,
                login_method=login_method,
                login_status=login_status,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason=failure_reason
            )
        except Exception as e:
            logger.error(f"Failed to create login log: {str(e)}")

    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class StaffLogoutView(APIView):
    """Handle staff logout"""
    
    def post(self, request):
        """Logout staff member and update log"""
        try:
            staff_id = request.data.get('staff_id')
            business_id = request.data.get('business_id')
            
            if not staff_id or not business_id:
                return Response({
                    'success': False,
                    'message': 'Staff ID and Business ID are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update the last login log with logout time
            try:
                last_login = StaffLoginLogs.objects.filter(
                    staff_id_id=staff_id,
                    business_id_id=business_id,
                    login_status='SUCCESS'
                ).latest('login_time')
                
                # Calculate session duration
                session_duration = None
                if last_login.login_time:
                    duration = timezone.now() - last_login.login_time
                    session_duration = int(duration.total_seconds() / 60)  # Convert to minutes
                
                last_login.logout_time = timezone.now()
                last_login.session_duration_minutes = session_duration
                last_login.save(update_fields=['logout_time', 'session_duration_minutes'])
                
            except StaffLoginLogs.DoesNotExist:
                logger.warning(f"No login log found for staff {staff_id}")
            
            return Response({
                'success': True,
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Staff logout error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StaffNavigationView(APIView):
    """Get staff navigation items based on role"""
    
    def get(self, request):
        """Get navigation items for logged-in staff"""
        try:
            staff_id = request.query_params.get('staff_id')
            business_id = request.query_params.get('business_id')
            
            if not staff_id or not business_id:
                return Response({
                    'success': False,
                    'message': 'Staff ID and Business ID are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get staff member
            try:
                staff = BusinessStaff.objects.get(
                    staff_id=staff_id,
                    business_id=business_id,
                    status=True
                )
            except BusinessStaff.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Staff member not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get navigation items based on staff's nav_items
            nav_items_ids = staff.nav_items or []
            print(f"[DEBUG] Staff nav_items: {nav_items_ids}")
            print(f"[DEBUG] Staff nav_items type: {type(nav_items_ids)}")
            print(f"[DEBUG] Staff details: ID={staff.staff_id}, Name={staff.full_name}")
            navigation_items = []
            
            # Check if nav_items is empty
            if not nav_items_ids:
                print("[DEBUG] No navigation items assigned to staff")
            else:
                print(f"[DEBUG] Processing {len(nav_items_ids)} navigation item IDs")
            
            if nav_items_ids:
                # Get all assigned navigation items (both parents and children)
                all_assigned_items = RoleBasedNavItems.objects.filter(
                    id__in=nav_items_ids,
                    status=True,
                    is_visible=True
                ).order_by('order_index')
                print(f"[DEBUG] Found {all_assigned_items.count()} items for nav_ids {nav_items_ids}")
                for item in all_assigned_items:
                    print(f"[DEBUG] Item: {item.id} - {item.nav_name} (parent: {item.parent_id}, status: {item.status}, visible: {item.is_visible})")
                
                # Also check what items exist with these IDs regardless of status/visibility
                all_items_any_status = RoleBasedNavItems.objects.filter(
                    id__in=nav_items_ids
                ).order_by('order_index')
                print(f"[DEBUG] Total items with these IDs (any status): {all_items_any_status.count()}")
                for item in all_items_any_status:
                    print(f"[DEBUG] Any Status Item: {item.id} - {item.nav_name} (status: {item.status}, visible: {item.is_visible})")
                
                # Separate parent and child items
                parent_items = all_assigned_items.filter(parent__isnull=True)
                child_items = all_assigned_items.filter(parent__isnull=False)
                
                # Track which children are already included under parents
                included_child_ids = set()
                
                # Build hierarchical structure for parent items
                for parent in parent_items:
                    parent_data = {
                        'id': parent.id,
                        'nav_name': parent.nav_name,
                        'icon': parent.icon,
                        'route_path': parent.route_path,
                        'order_index': parent.order_index,
                        'children': []
                    }
                    
                    # Get children for this parent that are also assigned to staff
                    children = child_items.filter(parent_id=parent.id)
                    
                    for child in children:
                        parent_data['children'].append({
                            'id': child.id,
                            'nav_name': child.nav_name,
                            'sub_nav': child.sub_nav,
                            'icon': child.icon,
                            'route_path': child.route_path,
                            'order_index': child.order_index
                        })
                        included_child_ids.add(child.id)
                    
                    navigation_items.append(parent_data)
                
                # Add standalone child items (whose parents are not assigned to staff)
                standalone_children = child_items.exclude(id__in=included_child_ids)
                for child in standalone_children:
                    navigation_items.append({
                        'id': child.id,
                        'nav_name': child.nav_name,
                        'sub_nav': child.sub_nav,
                        'icon': child.icon,
                        'route_path': child.route_path,
                        'order_index': child.order_index,
                        'children': []
                    })
            
            # Get display items for each navigation item
            from .serializers import NavDisplayItemSerializer
            display_items_by_nav = {}
            for nav_id in nav_items_ids:
                try:
                    nav = RoleBasedNavItems.objects.get(id=nav_id)
                    items = NavDisplayItem.objects.filter(
                        nav_item=nav,
                        status=True
                    ).order_by('order_index')
                    
                    # Filter premium items not purchased
                    filtered_items = []
                    for item in items:
                        if item.is_premium:
                            if BusinessFeaturePurchase.objects.filter(
                                business_id=staff.business_id,
                                feature_key=item.key,
                                status='ACTIVE'
                            ).exists() and BusinessFeaturePurchase.objects.get(
                                business_id=staff.business_id,
                                feature_key=item.key,
                                status='ACTIVE'
                            ).is_active():
                                filtered_items.append(item)
                        else:
                            filtered_items.append(item)
                    
                    # Only add to display_items if there are actual items
                    if filtered_items:
                        display_items_by_nav[nav_id] = NavDisplayItemSerializer(
                            filtered_items, 
                            many=True, 
                            context={'request': request}
                        ).data
                except RoleBasedNavItems.DoesNotExist:
                    pass  # Skip if nav item doesn't exist
            
            # Get business owner user_id
            business_owner_id = None
            try:
                business_mapping = staff.business_id.user_mappings.first()
                if business_mapping:
                    business_owner_id = business_mapping.user.user_id
            except:
                pass
            
            return Response({
                'success': True,
                'data': {
                    'staff_id': staff.staff_id,
                    'business_id': staff.business_id.business_id,
                    'business_name': staff.business_id.businessName,
                    'business_type': staff.business_id.businessType,
                    'business_owner_id': business_owner_id,
                    'staff_name': staff.full_name,
                    'role': staff.role,
                    'email': staff.email,
                    'mobile_number': staff.mobile_number or staff.phone,
                    'phone': staff.phone,
                    'last_login': staff.last_login,
                    'status': staff.status,
                    'navigation_items': navigation_items,
                    'display_items': display_items_by_nav
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Staff navigation error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DefaultNavbarView(APIView):
    """Get all navigation items from database without any conditions"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        """Get all navigation items from role_based_nav_items table without restrictions"""
        try:
            # Get all navigation items from database without any conditions
            all_nav_items = RoleBasedNavItems.objects.all().order_by('order_index', 'id')
            
            # Separate parent and child items
            parent_items = []
            child_items = []
            
            for item in all_nav_items:
                item_data = {
                    'id': item.id,
                    'nav_name': item.nav_name,
                    'sub_nav': item.sub_nav,
                    'status': item.status,
                    'is_visible': item.is_visible,
                    'parent_id': item.parent_id if item.parent else None,
                    'order_index': item.order_index,
                    'icon': item.icon,
                    'route_path': item.route_path,
                    'created_at': item.created_at.isoformat() if item.created_at else None,
                    'updated_at': item.updated_at.isoformat() if item.updated_at else None
                }
                
                if item.parent_id is None:
                    parent_items.append(item_data)
                else:
                    child_items.append(item_data)
            
            # Build hierarchical structure
            navigation_items = []
            for parent in parent_items:
                parent_data = {
                    'id': parent['id'],
                    'nav_name': parent['nav_name'],
                    'sub_nav': parent['sub_nav'],
                    'status': parent['status'],
                    'is_visible': parent['is_visible'],
                    'parent_id': parent['parent_id'],
                    'order_index': parent['order_index'],
                    'icon': parent['icon'],
                    'route_path': parent['route_path'],
                    'created_at': parent['created_at'],
                    'updated_at': parent['updated_at'],
                    'children': []
                }
                
                # Find children for this parent
                for child in child_items:
                    if child['parent_id'] == parent['id']:
                        parent_data['children'].append({
                            'id': child['id'],
                            'nav_name': child['nav_name'],
                            'sub_nav': child['sub_nav'],
                            'status': child['status'],
                            'is_visible': child['is_visible'],
                            'parent_id': child['parent_id'],
                            'order_index': child['order_index'],
                            'icon': child['icon'],
                            'route_path': child['route_path'],
                            'created_at': child['created_at'],
                            'updated_at': child['updated_at']
                        })
                
                # Sort children by order_index
                parent_data['children'].sort(key=lambda x: x['order_index'])
                navigation_items.append(parent_data)
            
            return Response({
                'success': True,
                'data': {
                    'navigation_items': navigation_items,
                    'total_count': len(all_nav_items)
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Default navbar error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BusinessFeaturePurchasesView(APIView):
    """Get all feature purchases for a business"""
    
    def get(self, request):
        try:
            business_id = request.query_params.get('business_id')
            if not business_id:
                return Response({
                    'success': False,
                    'message': 'Business ID is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            purchases = BusinessFeaturePurchase.objects.filter(
                business_id=business_id
            ).order_by('-purchased_at')
            
            from .serializers import BusinessFeaturePurchaseSerializer
            serializer = BusinessFeaturePurchaseSerializer(purchases, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Business feature purchases error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
