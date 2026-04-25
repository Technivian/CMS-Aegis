from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0034_search_preset'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['recipient', 'is_read', '-created_at'], name='notif_rec_read_created_ix'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['recipient', '-created_at'], name='notif_rec_created_ix'),
        ),
        migrations.AddIndex(
            model_name='searchpreset',
            index=models.Index(fields=['organization', 'created_by', 'name'], name='searchpreset_org_user_name_ix'),
        ),
        migrations.AddIndex(
            model_name='searchpreset',
            index=models.Index(fields=['organization', 'name'], name='searchpreset_org_name_ix'),
        ),
    ]
