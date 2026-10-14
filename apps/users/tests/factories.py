import factory
from apps.users.models import User, Address


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    role = User.Role.CUSTOMER
    is_verified = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password', 'DefaultPass123!')
        user = model_class(*args, **kwargs)
        user.set_password(password)
        user.save()
        return user


class AddressFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Address

    user = factory.SubFactory(UserFactory)
    label = "Home"
    street_line_1 = factory.Faker('street_address')
    city = factory.Faker('city')
    state_province = factory.Faker('state')
    postal_code = factory.Faker('postcode')
    country_code = "US"
    is_default = False
