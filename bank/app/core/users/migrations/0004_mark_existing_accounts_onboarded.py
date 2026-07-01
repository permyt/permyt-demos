from django.db import migrations


def mark_existing_onboarded(apps, schema_editor):
    """Accounts that already have an identity (created before the PERMYT
    onboarding flow, or otherwise populated) are considered onboarded — so
    they don't re-trigger an identity request and hang on the dashboard."""
    User = apps.get_model("users", "User")
    User.objects.exclude(full_name="").filter(onboarding_complete=False).update(
        onboarding_complete=True
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_user_address_user_birthdate_user_onboarding_complete_and_more"),
    ]

    operations = [
        migrations.RunPython(mark_existing_onboarded, noop),
    ]
