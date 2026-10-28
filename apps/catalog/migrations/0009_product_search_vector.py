from django.db import migrations


SEARCH_EXPRESSION = (
    "to_tsvector('simple'::regconfig, "
    "coalesce(name, '') || ' ' || coalesce(description, ''))"
)


def create_search_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(
        f"ALTER TABLE products ADD COLUMN IF NOT EXISTS search_vector tsvector "
        f"GENERATED ALWAYS AS ({SEARCH_EXPRESSION}) STORED"
    )
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS products_search_vector_gin "
        "ON products USING GIN (search_vector)"
    )


def drop_search_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("DROP INDEX IF EXISTS products_search_vector_gin")
    schema_editor.execute("ALTER TABLE products DROP COLUMN IF EXISTS search_vector")


class Migration(migrations.Migration):
    dependencies = [
        ('catalog', '0008_productimage_image_data_alter_productimage_image'),
    ]

    operations = [
        migrations.RunPython(create_search_index, drop_search_index),
    ]
