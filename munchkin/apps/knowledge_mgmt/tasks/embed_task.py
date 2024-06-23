import elasticsearch
from celery import shared_task
from dotenv import load_dotenv
from langchain_elasticsearch import ElasticsearchStore
from langserve import RemoteRunnable
from loguru import logger
from tqdm import tqdm

from apps.knowledge_mgmt.models import FileKnowledge, KnowledgeBaseFolder, ManualKnowledge, WebPageKnowledge
from apps.model_provider_mgmt.services.remote_embeddings import RemoteEmbeddings
from munchkin.components.elasticsearch import ELASTICSEARCH_PASSWORD, ELASTICSEARCH_URL

load_dotenv()


@shared_task
def general_embed(knowledge_base_folder_id):
    logger.info(f"开始生成知识库[{knowledge_base_folder_id}]的Embedding索引")

    knowledge_base_folder = KnowledgeBaseFolder.objects.get(id=knowledge_base_folder_id)
    index_name = knowledge_base_folder.knowledge_index_name()

    logger.info(f"初始化索引: {index_name}")
    es = elasticsearch.Elasticsearch(hosts=[ELASTICSEARCH_URL], basic_auth=("elastic", ELASTICSEARCH_PASSWORD))

    if es.indices.exists(index=index_name):
        logger.info(f"删除已存在的索引: {index_name}")
        es.indices.delete(index=index_name)

    try:
        knowledge_base_folder.train_status = 1
        knowledge_base_folder.train_progress = 0
        knowledge_base_folder.save()

        logger.info(f"获取Embedding模型: {knowledge_base_folder.embed_model}")

        knowledges = []

        file_knowledges = FileKnowledge.objects.filter(knowledge_base_folder=knowledge_base_folder).all()
        logger.info(f"知识库[{knowledge_base_folder_id}]包含[{len(file_knowledges)}]个文件知识")
        for obj in file_knowledges:
            knowledges.append(obj)

        manual_knowledges = ManualKnowledge.objects.filter(knowledge_base_folder=knowledge_base_folder).all()
        logger.info(f"知识库[{knowledge_base_folder_id}]包含[{len(manual_knowledges)}]个手动知识")
        for obj in manual_knowledges:
            knowledges.append(obj)

        web_page_knowledges = WebPageKnowledge.objects.filter(knowledge_base_folder=knowledge_base_folder).all()
        logger.info(f"知识库[{knowledge_base_folder_id}]包含[{len(web_page_knowledges)}]个网页知识")
        for obj in web_page_knowledges:
            knowledges.append(obj)

        file_remote = RemoteRunnable('http://chunk-server.ops-pilot:8104/file_chunk')
        manual_remote = RemoteRunnable('http://chunk-server.ops-pilot:8104/manual_chunk')
        web_page_remote = RemoteRunnable('http://chunk-server.ops-pilot:8104/webpage_chunk')

        total_knowledges = len(knowledges)
        for index, knowledge in tqdm(enumerate(knowledges)):
            knowledge_docs = []
            embedding_service = RemoteEmbeddings(knowledge_base_folder.embed_model)
            if isinstance(knowledge, FileKnowledge):
                logger.debug(f"开始处理文件知识: {knowledge.title}")
                semantic_embedding_address = ''

                semantic_chunk_parse_embedding_model = knowledge_base_folder.semantic_chunk_parse_embedding_model
                if semantic_chunk_parse_embedding_model is not None:
                    semantic_embedding_address = semantic_chunk_parse_embedding_model.embed_config["base_url"]

                remote_docs = file_remote.invoke({
                    "enable_recursive_chunk_parse": knowledge_base_folder.enable_general_parse,
                    "recursive_chunk_size": knowledge_base_folder.general_parse_chunk_size,
                    "recursive_chunk_overlap": knowledge_base_folder.general_parse_chunk_overlap,
                    "enable_semantic_chunck_parse": knowledge_base_folder.enable_semantic_chunck_parse,
                    "semantic_embedding_address": semantic_embedding_address,
                    "file_name": knowledge.file.name,
                    "file": knowledge.get_file_base64(),
                    "custom_metadata": {
                        "knowledge_type": "file",
                    },
                })
                knowledge_docs.extend(remote_docs)
                logger.info(f"文件知识[{knowledge.title}]共提取[{len(remote_docs)}]个文档片段")

            elif isinstance(knowledge, ManualKnowledge):
                logger.debug(f"开始处理手动知识: {knowledge.title}")
                remote_docs = manual_remote.invoke({
                    "enable_recursive_chunk_parse": knowledge_base_folder.enable_general_parse,
                    "recursive_chunk_size": knowledge_base_folder.general_parse_chunk_size,
                    "recursive_chunk_overlap": knowledge_base_folder.general_parse_chunk_overlap,
                    "enable_semantic_chunck_parse": knowledge_base_folder.enable_semantic_chunck_parse,
                    "semantic_embedding_address":
                        knowledge_base_folder.semantic_chunk_parse_embedding_model.decrypted_embed_config["base_url"],
                    "content": knowledge.content,
                    "custom_metadata": {
                        "knowledge_type": "manual",
                    },
                })
                knowledge_docs.extend(remote_docs)
                logger.info(f"手动知识[{knowledge.title}]共提取[{len(remote_docs)}]个文档片段")

            elif isinstance(knowledge, WebPageKnowledge):
                logger.debug(f"开始处理网页知识: {knowledge.title}")
                web_page_remote.invoke({
                    "enable_recursive_chunk_parse": knowledge_base_folder.enable_general_parse,
                    "recursive_chunk_size": knowledge_base_folder.general_parse_chunk_size,
                    "recursive_chunk_overlap": knowledge_base_folder.general_parse_chunk_overlap,
                    "enable_semantic_chunck_parse": knowledge_base_folder.enable_semantic_chunck_parse,
                    "semantic_embedding_address":
                        knowledge_base_folder.semantic_chunk_parse_embedding_model.decrypted_embed_config["base_url"],
                    "url": knowledge.url,
                    "max_depth": 1,
                    "custom_metadata": {
                        "knowledge_type": "webpage",
                    },
                })
                knowledge_docs.extend(remote_docs)
                logger.info(f"网页知识[{knowledge.title}]共提取[{len(remote_docs)}]个文档片段")

            for doc in knowledge_docs:
                doc.metadata["knowledge_id"] = knowledge.id
                doc.metadata["knowledge_folder_id"] = knowledge_base_folder_id
                doc.metadata["knowledge_title"] = knowledge.title
                for key, value in knowledge.custom_metadata.items():
                    doc.metadata[key] = value

            logger.debug(f"开始生成知识库[{knowledge_base_folder_id}]的Embedding索引")

            db = ElasticsearchStore.from_documents(
                knowledge_docs, embedding=embedding_service, es_connection=es, index_name=index_name
            )
            db.client.indices.refresh(index=index_name)

            progress = round((index + 1) / total_knowledges * 100, 2)
            logger.debug(f"知识库[{knowledge_base_folder_id}]的Embedding索引生成进度: {progress:.2f}%")
            knowledge_base_folder.train_progress = progress
            knowledge_base_folder.save()

        knowledge_base_folder.train_status = 2
        knowledge_base_folder.train_progress = 100
        knowledge_base_folder.save()

    except Exception as e:
        logger.exception(e)

        knowledge_base_folder.train_status = 3
        knowledge_base_folder.train_progress = 100
        knowledge_base_folder.save()
