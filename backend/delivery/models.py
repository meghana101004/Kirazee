# delivery/models.py
from django.db import models
from geopy.distance import geodesic
from django.conf import settings
from django.utils import timezone
from kirazee_app.models import Registration
from consumer.models import Orders
from consumer.gro_models import GroceriesOrders
import random
import string
from django.core.cache import cache

class DeliveryPartner(models.Model):
    VEHICLE_TYPES = [
        ('bike', 'Bike'),
        ('scooter', 'Scooter'),
        ('car', 'Car'),
        ('bicycle', 'Bicycle')
    ]
    
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('on_delivery', 'On Delivery'),
        ('offline', 'Offline')
    ]
    
    user = models.OneToOneField(
        Registration,
        to_field='user_id',
        db_column='user_id',
        on_delete=models.CASCADE,
        related_name='delivery_partner'
    )
    business_id = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPES)
    vehicle_number = models.CharField(max_length=20)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    is_available = models.BooleanField(default=True)
    rating = models.FloatField(default=0.0)
    total_deliveries = models.IntegerField(default=0)
    phone_number = models.CharField(max_length=15)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'delivery_partner'

    def __str__(self):
        try:
            first = getattr(self.user, 'firstName', '') or ''
            last = getattr(self.user, 'lastName', '') or ''
            name = (first + ' ' + last).strip() or str(getattr(self.user, 'user_id', ''))
        except Exception:
            name = str(getattr(self.user, 'user_id', ''))
        return f"{name} - {self.vehicle_type}"

    @property
    def current_location(self):
        """Return coordinates as a tuple (lat, lng) if available"""
        if self.latitude is not None and self.longitude is not None:
            return (self.latitude, self.longitude)
        return None

    @current_location.setter
    def current_location(self, coordinates):
        """Set coordinates from a tuple (lat, lng)"""
        if coordinates and len(coordinates) == 2:
            self.latitude, self.longitude = coordinates

class DeliveryLocationHistory(models.Model):
    delivery_partner = models.ForeignKey(
        DeliveryPartner, 
        on_delete=models.CASCADE,
        related_name='location_history'
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'deliverylocationhistory'
        ordering = ['-timestamp']

    def location(self):
        """Return coordinates as a tuple (lat, lng)"""
        return (self.latitude, self.longitude)

class OrderOTP(models.Model):
    order_id = models.BigIntegerField(db_index=True, help_text="Reference to the order id across systems")
    otp = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def generate_otp(cls, order_id, expiry_minutes=10):
        otp_code = ''.join(random.choices(string.digits, k=6))
        expires_at = timezone.now() + timezone.timedelta(minutes=expiry_minutes) if expiry_minutes else None
        return cls.objects.create(
            order_id=order_id,
            otp=otp_code,
            expires_at=expires_at
        )

    def refresh_otp(self, expiry_minutes=10):
        self.otp = ''.join(random.choices(string.digits, k=6))
        self.is_verified = False
        self.expires_at = timezone.now() + timezone.timedelta(minutes=expiry_minutes) if expiry_minutes else None
        self.save(update_fields=['otp', 'is_verified', 'expires_at', 'updated_at'])
        return self.otp

    def is_expired(self):
        return bool(self.expires_at and timezone.now() > self.expires_at)

    def mark_verified(self):
        if not self.is_verified:
            self.is_verified = True
            self.save(update_fields=['is_verified', 'updated_at'])

    class Meta:
        db_table = 'delivery_orderotp'
        indexes = [
            models.Index(fields=['order_id'], name='idx_orderotp_order')
        ]