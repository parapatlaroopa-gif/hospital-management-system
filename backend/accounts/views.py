from rest_framework import status, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from .models import UserProfile, PatientAssignment
from .serializers import UserSerializer, PatientRegisterSerializer, RecruitStaffSerializer, PatientAssignmentSerializer
from accounts.permissions import IsAdmin, IsClinicalStaff
from patients.models import Patient
from doctors.models import Doctor
from staff.models import Staff


def ensure_user_profile_linkage(user):
    """
    Ensures that a user's UserProfile is linked to the corresponding
    Patient, Doctor, or Staff record based on their role.
    If no record exists, one is automatically created so appointments
    and dashboards work seamlessly without missing-profile errors.
    """
    if not user or not user.is_authenticated:
        return None

    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={"role": "ADMIN" if user.is_superuser else "PATIENT"}
    )
    role = (profile.role or "PATIENT").upper()

    if role == "PATIENT":
        if not profile.patient:
            patient = None
            if profile.phone:
                patient = Patient.objects.filter(phone=profile.phone).first()
            if not patient and (user.first_name or user.last_name):
                patient = Patient.objects.filter(
                    first_name__iexact=user.first_name,
                    last_name__iexact=user.last_name
                ).first()
            if not patient:
                patient = Patient.objects.create(
                    first_name=user.first_name or user.username or "Patient",
                    last_name=user.last_name or "",
                    age=30,
                    gender="Other",
                    phone=profile.phone or "9999999999",
                    address="CarePulse Registered Patient"
                )
            profile.patient = patient
            profile.save(update_fields=["patient"])
        return profile.patient

    elif role == "DOCTOR":
        if not profile.doctor:
            doc = None
            if user.email:
                doc = Doctor.objects.filter(email__iexact=user.email).first()
            if not doc and (user.first_name or user.last_name):
                doc = Doctor.objects.filter(
                    first_name__iexact=user.first_name,
                    last_name__iexact=user.last_name
                ).first()
            if not doc:
                doc = Doctor.objects.create(
                    first_name=user.first_name or user.username or "Doctor",
                    last_name=user.last_name or "",
                    specialization="General Physician",
                    phone=profile.phone or "9999999999",
                    email=user.email or f"{user.username}@hospital.com",
                    experience=5,
                    room_number="101"
                )
            profile.doctor = doc
            profile.save(update_fields=["doctor"])
        return profile.doctor

    elif role == "NURSE":
        if not profile.staff:
            stf = None
            if user.email:
                stf = Staff.objects.filter(email__iexact=user.email).first()
            if not stf and (user.first_name or user.last_name):
                stf = Staff.objects.filter(
                    first_name__iexact=user.first_name,
                    last_name__iexact=user.last_name
                ).first()
            if not stf:
                from datetime import date
                stf = Staff.objects.create(
                    first_name=user.first_name or user.username or "Nurse",
                    last_name=user.last_name or "",
                    role="Nurse",
                    phone=profile.phone or "9999999999",
                    email=user.email or f"{user.username}@hospital.com",
                    salary=35000.00,
                    joining_date=date.today()
                )
            profile.staff = stf
            profile.save(update_fields=["staff"])
        return profile.staff

    elif role == "ADMIN":
        if not profile.patient:
            admin_patient = None
            if profile.phone:
                admin_patient = Patient.objects.filter(phone=profile.phone).first()
            if not admin_patient and (user.first_name or user.last_name):
                admin_patient = Patient.objects.filter(
                    first_name__iexact=user.first_name,
                    last_name__iexact=user.last_name
                ).first()
            if not admin_patient:
                admin_patient = Patient.objects.create(
                    first_name=user.first_name or "Hospital",
                    last_name=user.last_name or "Administrator",
                    age=30,
                    gender="Other",
                    phone=profile.phone or "9999999999",
                    address="CarePulse Hospital Directorate"
                )
            profile.patient = admin_patient
            profile.save(update_fields=["patient"])
        return profile.patient

    return None


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        identifier = (request.data.get("email") or request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        if not identifier or not password:
            return Response({"error": "Please provide both email/username and password."}, status=400)

        user = authenticate(username=identifier, password=password)
        if not user:
            user_obj = User.objects.filter(email__iexact=identifier).first()
            if user_obj:
                user = authenticate(username=user_obj.username, password=password)
        if not user:
            return Response({"error": "Invalid email/username or password."}, status=401)
        if not user.is_active:
            return Response({"error": "Your account has been deactivated. Please contact hospital administrator."}, status=403)

        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": "ADMIN" if user.is_superuser else "PATIENT"})
        if user.is_superuser and profile.role != "ADMIN":
            profile.role = "ADMIN"
            profile.save(update_fields=["role"])

        role = profile.role.upper()
        expected_role = (request.data.get("expected_role") or "").upper()
        if expected_role == "ADMIN" and role != "ADMIN":
            return Response({"error": "This console is restricted to Hospital Administrators only."}, status=403)

        # Ensure profile relations (patient_id, doctor_id, staff_id) are linked
        ensure_user_profile_linkage(user)
        user.refresh_from_db()

        redirect_url = {"ADMIN": "/admin/dashboard", "DOCTOR": "/staff/dashboard", "NURSE": "/staff/dashboard", "PATIENT": "/patient/dashboard"}.get(role, "/login")
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "message": "Login successful",
            "token": token.key,
            "user": UserSerializer(user).data,
            "role": role,
            "redirect_url": redirect_url,
        })


class PatientRegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PatientRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "Patient registered successfully. You can now log in.",
                "user": UserSerializer(user).data,
                "role": "PATIENT",
                "redirect_url": "/patient/dashboard",
            }, status=201)
        return Response(serializer.errors, status=400)


class RecruitStaffView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        try:
            serializer = RecruitStaffSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=400)

            with transaction.atomic():
                user = serializer.save()
                ensure_user_profile_linkage(user)
                user = User.objects.select_related("profile").get(id=user.id)

            return Response({
                "message": f"Successfully created {user.get_full_name()} as {request.data.get('role')}.",
                "user": UserSerializer(user).data,
            }, status=201)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        ensure_user_profile_linkage(request.user)
        request.user.refresh_from_db()
        return Response(UserSerializer(request.user).data)


class UserListView(generics.ListAPIView):
    permission_classes = [IsAdmin]
    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        role = self.request.query_params.get("role")
        return qs.filter(profile__role__iexact=role) if role else qs


class UserToggleActiveView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)
        if user == request.user:
            return Response({"error": "You cannot deactivate your own admin account."}, status=400)
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        return Response({"message": f"User is now {'active' if user.is_active else 'inactive'}.", "is_active": user.is_active})


class UserDetailDestroyView(generics.RetrieveDestroyAPIView):
    permission_classes = [IsAdmin]
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def perform_destroy(self, instance):
        from rest_framework import exceptions
        if instance == self.request.user:
            raise exceptions.ValidationError("You cannot delete your own logged-in admin account.")
        if instance.email == "nithinkumarreddy1538@gmail.com":
            raise exceptions.ValidationError("Primary Administrator account cannot be deleted.")

        # Clean up linked entity profiles
        profile = getattr(instance, "profile", None)
        if profile:
            if profile.patient:
                profile.patient.delete()
            if profile.doctor:
                profile.doctor.delete()
            if profile.staff:
                profile.staff.delete()

        instance.delete()


class PatientAssignmentListCreateView(generics.ListCreateAPIView):
    serializer_class = PatientAssignmentSerializer
    permission_classes = [IsAdmin | IsClinicalStaff]

    def get_queryset(self):
        qs = PatientAssignment.objects.all().order_by("-assigned_date", "-created_at")
        profile = getattr(self.request.user, "profile", None)
        if profile and profile.role == "DOCTOR" and getattr(profile, "doctor_id", None):
            return qs.filter(doctor_id=profile.doctor_id)
        if profile and profile.role == "NURSE" and getattr(profile, "staff_id", None):
            return qs.filter(nurse_id=profile.staff_id)
        doctor_id = self.request.query_params.get("doctor_id")
        nurse_id = self.request.query_params.get("nurse_id")
        patient_id = self.request.query_params.get("patient_id")
        if doctor_id: qs = qs.filter(doctor_id=doctor_id)
        if nurse_id: qs = qs.filter(nurse_id=nurse_id)
        if patient_id: qs = qs.filter(patient_id=patient_id)
        return qs

    def perform_create(self, serializer):
        profile = getattr(self.request.user, "profile", None)
        if profile and profile.role == "DOCTOR" and getattr(profile, "doctor", None):
            serializer.save(doctor=profile.doctor)
        else:
            serializer.save()


class PatientAssignmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PatientAssignmentSerializer
    permission_classes = [IsAdmin | IsClinicalStaff]

    def get_queryset(self):
        qs = PatientAssignment.objects.all()
        profile = getattr(self.request.user, "profile", None)
        if profile and profile.role == "DOCTOR" and getattr(profile, "doctor_id", None):
            qs = qs.filter(doctor_id=profile.doctor_id)
        elif profile and profile.role == "NURSE" and getattr(profile, "staff_id", None):
            qs = qs.filter(nurse_id=profile.staff_id)
        return qs

