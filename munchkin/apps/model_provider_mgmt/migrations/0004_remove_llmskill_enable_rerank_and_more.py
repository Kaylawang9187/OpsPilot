# Generated by Django 4.2.7 on 2024-06-06 05:52

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('model_provider_mgmt', '0003_remove_llmskill_rag_num_candidates_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='llmskill',
            name='enable_rerank',
        ),
        migrations.RemoveField(
            model_name='llmskill',
            name='rerank_model',
        ),
        migrations.RemoveField(
            model_name='llmskill',
            name='rerank_top_k',
        ),
    ]