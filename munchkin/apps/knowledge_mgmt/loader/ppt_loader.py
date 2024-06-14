from typing import List

from langchain_community.document_loaders import UnstructuredFileLoader


class PPTLoader(UnstructuredFileLoader):
    def _get_elements(self) -> List:
        from unstructured.partition.text import partition_text
        from apps.knowledge_mgmt.utils.ppt import ppt2text

        text = ppt2text(self.file_path)
        return partition_text(text=text, **self.unstructured_kwargs)
