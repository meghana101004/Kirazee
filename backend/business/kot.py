from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from drf_yasg.utils import swagger_auto_schema
import json
from datetime import datetime, date
from decimal import Decimal

def _parse_permissions(value):
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None

def _row_to_dict(row, columns):
    return {columns[i]: row[i] for i in range(len(columns))}

def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    return str(o)

def _fetch_brm_row(brm_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, business_id, assigned_by, assigned_to, role, username, password, permissions, status, created_at, updated_at
            FROM business_role_management
            WHERE id = %s
            """,
            [brm_id],
        )
        row = cursor.fetchone()
        if not row:
            return None
        cols = [
            "id",
            "business_id",
            "assigned_by",
            "assigned_to",
            "role",
            "username",
            "password",
            "permissions",
            "status",
            "created_at",
            "updated_at",
        ]
        data = _row_to_dict(row, cols)
        try:
            if isinstance(data.get("permissions"), (bytes, bytearray)):
                data["permissions"] = data["permissions"].decode("utf-8")
            if isinstance(data.get("permissions"), str):
                data["permissions"] = json.loads(data["permissions"]) if data["permissions"] else None
        except Exception:
            data["permissions"] = None
        return data

def _log_brm_action(brm_id, user_id, action_type, old_data, new_data):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO business_role_management_log (id, user_id, action_type, old_data, new_data)
            VALUES (%s, %s, %s, CAST(%s AS JSON), CAST(%s AS JSON))
            """,
            [
                brm_id,
                user_id,
                action_type,
                json.dumps(old_data, default=_json_default) if old_data is not None else None,
                json.dumps(new_data, default=_json_default) if new_data is not None else None,
            ],
        )

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(["POST"])
def assign_kot(request):
    try:
        business_id = request.data.get("business_id")
        assigned_to = request.data.get("assigned_to")
        username = request.data.get("username")
        password = request.data.get("password")
        assigned_by = request.data.get("assigned_by")
        role = request.data.get("role") or "KOT"
        status_flag = request.data.get("status")
        permissions = _parse_permissions(request.data.get("permissions"))

        if not business_id or not assigned_to or not username or password is None:
            return Response(
                {"success": False, "message": "business_id, assigned_to, username, password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO business_role_management
                (business_id, assigned_by, assigned_to, role, username, password, permissions, status)
                VALUES (%s, %s, %s, %s, %s, %s, CAST(%s AS JSON), %s)
                """,
                [
                    business_id,
                    assigned_by,
                    assigned_to,
                    role,
                    username,
                    password,
                    json.dumps(permissions) if permissions is not None else None,
                    int(status_flag) if str(status_flag).isdigit() else 1,
                ],
            )
            new_id = cursor.lastrowid

        new_row = _fetch_brm_row(new_id)
        _log_brm_action(new_id, assigned_by, "INSERT", None, new_row)

        return Response(
            {"success": True, "message": "KOT assigned successfully", "data": new_row},
            status=status.HTTP_201_CREATED,
        )
    except Exception as e:
        return Response({"success": False, "message": f"Error assigning KOT: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(["GET"])
def list_kot_users(request):
    try:
        business_id = request.GET.get("business_id")
        role = request.GET.get("role") or "KOT"
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 50)), 100)
        offset = (page - 1) * limit
        if not business_id:
            return Response({"success": False, "message": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM business_role_management brm
                WHERE brm.business_id = %s AND brm.role = %s
                """,
                [business_id, role],
            )
            total = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT 
                    brm.id, brm.business_id, brm.assigned_by, brm.assigned_to, brm.role,
                    brm.username, brm.password, brm.permissions, brm.status,
                    brm.created_at, brm.updated_at,
                    r.displayName, r.mobileNumber, r.emailID
                FROM business_role_management brm
                LEFT JOIN registrations r ON brm.assigned_to = r.user_id
                WHERE brm.business_id = %s AND brm.role = %s
                ORDER BY brm.created_at DESC
                LIMIT %s OFFSET %s
                """,
                [business_id, role, limit, offset],
            )
            rows = cursor.fetchall()

        results = []
        for row in rows:
            data = {
                "id": row[0],
                "business_id": row[1],
                "assigned_by": row[2],
                "assigned_to": row[3],
                "role": row[4],
                "username": row[5],
                "password": row[6],
                "permissions": None,
                "status": row[8],
                "created_at": row[9],
                "updated_at": row[10],
                "user": {
                    "display_name": row[11],
                    "mobile": row[12],
                    "email": row[13],
                },
            }
            try:
                perm_val = row[7]
                if isinstance(perm_val, (bytes, bytearray)):
                    perm_val = perm_val.decode("utf-8")
                data["permissions"] = json.loads(perm_val) if perm_val else None
            except Exception:
                data["permissions"] = None
            results.append(data)

        total_pages = (total + limit - 1) // limit
        return Response(
            {
                "success": True,
                "message": "KOT users retrieved successfully",
                "pagination": {
                    "total": total,
                    "current_page": page,
                    "per_page": limit,
                    "total_pages": total_pages,
                    "has_next_page": page < total_pages,
                    "has_prev_page": page > 1,
                },
                "data": results,
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response({"success": False, "message": f"Error retrieving KOT users: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['PUT', 'PATCH'], tags=['Business'])
@api_view(["PUT", "PATCH"])
def update_kot_user(request, id):
    try:
        actor_user_id = request.data.get("performed_by")
        old_row = _fetch_brm_row(id)
        if not old_row:
            return Response({"success": False, "message": "KOT record not found"}, status=status.HTTP_404_NOT_FOUND)

        fields = {}
        for key in ["assigned_by", "assigned_to", "role", "username", "password", "status"]:
            if key in request.data:
                fields[key] = request.data.get(key)
        if "permissions" in request.data:
            fields["permissions"] = _parse_permissions(request.data.get("permissions"))

        if not fields:
            return Response({"success": False, "message": "No fields to update"}, status=status.HTTP_400_BAD_REQUEST)

        sets = []
        params = []
        for k, v in fields.items():
            if k == "permissions":
                sets.append("permissions = CAST(%s AS JSON)")
                params.append(json.dumps(v) if v is not None else None)
            else:
                sets.append(f"{k} = %s")
                params.append(v)
        params.append(id)

        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE business_role_management SET {', '.join(sets)} WHERE id = %s",
                params,
            )

        new_row = _fetch_brm_row(id)
        _log_brm_action(id, actor_user_id, "UPDATE", old_row, new_row)

        return Response({"success": True, "message": "KOT updated successfully", "data": new_row}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"success": False, "message": f"Error updating KOT: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['DELETE'], tags=['Business'])
@api_view(["DELETE"])
def delete_kot_user(request, id):
    try:
        actor_user_id = request.GET.get("performed_by") or request.data.get("performed_by")
        old_row = _fetch_brm_row(id)
        if not old_row:
            return Response({"success": False, "message": "KOT record not found"}, status=status.HTTP_404_NOT_FOUND)

        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM business_role_management WHERE id = %s", [id])

        _log_brm_action(id, actor_user_id, "DELETE", old_row, None)

        return Response({"success": True, "message": "KOT deleted successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"success": False, "message": f"Error deleting KOT: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(["POST"])
def kot_login(request):
    try:
        username = request.data.get("username")
        password = request.data.get("password")
        business_id = request.data.get("business_id")
        role = request.data.get("role")  # Optional - if not provided, accepts any role

        if not username or password is None:
            return Response(
                {"success": False, "message": "username and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        params = [username, password]
        where_clause = "brm.username = %s AND brm.password = %s AND brm.status = 1"
        
        # Only filter by role if explicitly provided
        if role:
            where_clause += " AND brm.role = %s"
            params.append(role)
            
        if business_id:
            where_clause += " AND brm.business_id COLLATE utf8mb4_0900_ai_ci = CAST(%s AS CHAR) COLLATE utf8mb4_0900_ai_ci"
            params.append(business_id)

        with connection.cursor() as cursor:
            # First, check if username exists at all
            cursor.execute(
                "SELECT id, username, role, status, business_id FROM business_role_management WHERE username = %s",
                [username]
            )
            debug_row = cursor.fetchone()
            
            # Log debug information
            print(f"[KOT LOGIN DEBUG] Username: {username}, Role filter: {role or 'Any'}, Business ID: {business_id or 'Any'}")
            if debug_row:
                print(f"[KOT LOGIN DEBUG] Found user - ID: {debug_row[0]}, Username: {debug_row[1]}, Role: {debug_row[2]}, Status: {debug_row[3]}, Business: {debug_row[4]}")
            else:
                print(f"[KOT LOGIN DEBUG] Username '{username}' not found in database")
            
            cursor.execute(
                f"""
                SELECT 
                    brm.id, brm.business_id, brm.assigned_by, brm.assigned_to, brm.role,
                    brm.username, brm.permissions, brm.status,
                    brm.created_at, brm.updated_at,
                    r.displayName, r.mobileNumber, r.emailID,
                    b.businessType, b.businessName
                FROM business_role_management brm
                LEFT JOIN registrations r ON brm.assigned_to = r.user_id
                LEFT JOIN businesses b ON b.business_id COLLATE utf8mb4_0900_ai_ci = brm.business_id COLLATE utf8mb4_0900_ai_ci
                WHERE {where_clause}
                ORDER BY brm.updated_at DESC
                LIMIT 1
                """,
                params,
            )
            row = cursor.fetchone()

        if not row:
            # Provide more specific error message
            if debug_row:
                if debug_row[3] != 1:
                    return Response({"success": False, "message": "Account is inactive"}, status=status.HTTP_401_UNAUTHORIZED)
                elif role and debug_row[2] != role:
                    return Response({"success": False, "message": f"Invalid role. Expected '{role}', found '{debug_row[2]}'"}, status=status.HTTP_401_UNAUTHORIZED)
                elif business_id and debug_row[4] != business_id:
                    return Response({"success": False, "message": "Business ID mismatch"}, status=status.HTTP_401_UNAUTHORIZED)
                else:
                    return Response({"success": False, "message": "Invalid password"}, status=status.HTTP_401_UNAUTHORIZED)
            else:
                return Response({"success": False, "message": "Username not found"}, status=status.HTTP_401_UNAUTHORIZED)

        permissions = None
        try:
            perm_val = row[6]
            if isinstance(perm_val, (bytes, bytearray)):
                perm_val = perm_val.decode("utf-8")
            permissions = json.loads(perm_val) if perm_val else None
        except Exception:
            permissions = None

        # Check if this business is a master and get sublevel businesses
        user_business_id = row[1]
        sublevel_businesses = []
        
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT business_id, businessName, businessType, level
                FROM businesses
                WHERE master = %s AND status = 1
                ORDER BY created_at DESC
                """,
                [user_business_id]
            )
            sublevel_rows = cursor.fetchall()
            
            for sub_row in sublevel_rows:
                sublevel_businesses.append({
                    "business_id": sub_row[0],
                    "business_name": sub_row[1],
                    "business_type": sub_row[2],
                    "level": sub_row[3]
                })
        
        print(f"[KOT LOGIN DEBUG] Found {len(sublevel_businesses)} sublevel businesses for master: {user_business_id}")

        data = {
            "id": row[0],
            "business_id": row[1],
            "assigned_by": row[2],
            "assigned_to": row[3],
            "role": row[4],
            "username": row[5],
            "permissions": permissions,
            "status": row[7],
            "created_at": row[8],
            "updated_at": row[9],
            "user": {
                "display_name": row[10],
                "mobile": row[11],
                "email": row[12],
            },
            "business": {
                "business_type": row[13],
                "business_name": row[14],
            },
            "sublevel_businesses": sublevel_businesses,
            "is_master": len(sublevel_businesses) > 0,
        }

        return Response({"success": True, "message": "Login successful", "data": data}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"success": False, "message": f"Error during KOT login: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

