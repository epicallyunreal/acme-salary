"""factory_boy factories. Small by construction: the minimum rows a test needs, never the seed."""

import factory
from django.contrib.auth import get_user_model


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()

    email = factory.Sequence(lambda n: f"user{n}@acme.example")
    password = factory.django.Password("correct-horse-battery")
