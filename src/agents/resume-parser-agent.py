# Complete Resume Parser Agent Code

import os
import tempfile
from google.cloud import storage
from pdfminer.high_level import extract_text
import docx

class ResumeParserAgent:
    def __init__(self):
        self.fact_bank = {}  # Immutable Fact Bank

    def upload_to_gcs(self, file_name, bucket_name):
        client = storage.Client()
        bucket = client.get_bucket(bucket_name)
        blob = bucket.blob(file_name)
        blob.upload_from_filename(file_name)

    def parse_pdf(self, file_path):
        return extract_text(file_path)

    def parse_docx(self, file_path):
        doc = docx.Document(file_path)
        return '
'.join([para.text for para in doc.paragraphs])

    def extract_facts(self, resume_content):
        # Extract facts from the resume_content
        # This function should parse the content and fill the fact_bank
        pass

    def run(self, file_path, bucket_name):
        if file_path.endswith('.pdf'):
            content = self.parse_pdf(file_path)
        elif file_path.endswith('.docx'):
            content = self.parse_docx(file_path)
        else:
            raise ValueError('Unsupported file format')

        self.extract_facts(content)
        self.upload_to_gcs(file_path, bucket_name)

# Standalone runner
if __name__ == '__main__':
    agent = ResumeParserAgent()
    agent.run('sample_resume.pdf', 'your-bucket-name')

# Sample resume content
# For testing purposes, a sample file should be created.