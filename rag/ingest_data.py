import os
import time
from pathlib import Path
from dotenv import load_dotenv

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Pinecone as PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec
from langchain_experimental.text_splitter import SemanticChunker
import uuid

# Load biến môi trường
load_dotenv()

class DataIngestion:
    def __init__(self):
        # Dùng SentenceTransformer local thay cho OpenAI
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        # Khởi tạo Pinecone
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "store-knowledge")

    def create_index_if_not_exists(self):
        """Tạo mới Pinecone index (xóa nếu đã tồn tại)"""
        existing_indexes = [index.name for index in self.pc.list_indexes()]

        if self.index_name in existing_indexes:
            print(f"Index {self.index_name} đã tồn tại — tiến hành xóa...")
            self.pc.delete_index(self.index_name)
            # Đợi một chút để Pinecone xử lý việc xóa
            time.sleep(3)
            print(f"Index {self.index_name} đã được xóa thành công")

        print(f"Tạo mới index: {self.index_name}")
        self.pc.create_index(
            name=self.index_name,
            dimension=384,  # phù hợp với all-MiniLM-L6-v2
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        # Chờ index sẵn sàng
        time.sleep(5)
        print(f"Index {self.index_name} đã được tạo thành công!")


    def load_documents_from_folder(self, folder_path: str):
        """Load tất cả file TXT từ folder"""
        documents = []
        folder = Path(folder_path)

        if not folder.exists():
            print(f"Folder {folder_path} không tồn tại!")
            return documents

        txt_files = list(folder.glob("*.txt"))
        print(f"Tìm thấy {len(txt_files)} file TXT")

        for txt_file in txt_files:
            try:
                loader = TextLoader(str(txt_file), encoding="utf-8")
                docs = loader.load()
                print(f"Loaded: {txt_file.name}")
                documents.extend(docs)
            except Exception as e:
                print(f"Lỗi khi load {txt_file.name}: {e}")

        return documents

    def split_documents(self, docs):
        print("Splitting documents semantically...")
        splitter = SemanticChunker(self.embeddings)  # dùng embedding để chia theo ý nghĩa
        splits = splitter.split_documents(docs)
        print(f"Total semantic chunks: {len(splits)}")
        return splits

    def ingest_to_pinecone(self, documents):
        """Đưa documents vào Pinecone Serverless v2 (vẫn giữ code gốc)"""
        print("Bắt đầu ingest vào Pinecone Serverless v2...")

        # Tạo hoặc kết nối index
        existing_indexes = [idx.name for idx in self.pc.list_indexes()]
        if self.index_name not in existing_indexes:
            print(f"Tạo index mới: {self.index_name}")
            self.pc.create_index(
                name=self.index_name,
                dimension=384,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
            time.sleep(5)  # chờ index sẵn sàng

        # Lấy reference đến index serverless
        index = self.pc.Index(self.index_name)

        # Batch upsert (vẫn giữ logic gốc)
        batch_size = 50
        vectors = []
        for i, doc in enumerate(documents):
            # tạo embedding
            embedding = self.embeddings.embed_query(doc.page_content)

            # tạo ID tự động (UUID)
            vector_id = str(uuid.uuid4())

            vectors.append({
                "id": vector_id,
                "values": embedding,
                "metadata": {
                    "category": "category_" + str(i + 1),
                    "content": doc.page_content
                }
            })

            if len(vectors) >= batch_size or i == len(documents) - 1:
                index.upsert(vectors=vectors)
                vectors = []

        print("Ingest hoàn tất!")

    def run_ingestion(self, data_folder: str = "./store_data"):
        """Chạy toàn bộ quá trình ingestion"""
        print("=" * 50)
        print("BẮT ĐẦU QUÁ TRÌNH INGESTION DATA")
        print("=" * 50)

        # 1. Tạo index
        self.create_index_if_not_exists()

        # 2. Load documents
        print("\n1. Loading documents...")
        documents = self.load_documents_from_folder(data_folder)

        if not documents:
            print("Không có documents nào để xử lý!")
            return

        print(f"Tổng số documents: {len(documents)}")

        # 3. Split documents
        print("\n2. Splitting documents...")
        splits = self.split_documents(documents)

        # 4. Ingest to Pinecone
        print("\n3. Ingesting to Pinecone...")
        self.ingest_to_pinecone(splits)

        print("\n" + "=" * 50)
        print("HOÀN TẤT QUÁ TRÌNH INGESTION!")
        print("=" * 50)


def main():
    """Main function để chạy ingestion"""
    ingestion = DataIngestion()

    # Đường dẫn đến folder chứa file TXT
    data_folder = "./store_data"

    # Tạo folder mẫu nếu chưa có
    os.makedirs(data_folder, exist_ok=True)

    # Tạo file mẫu
    sample_file = os.path.join(data_folder, "store_info.txt")
    if not os.path.exists(sample_file):
        with open(sample_file, "w", encoding="utf-8") as f:
            f.write("""Thông tin cửa hàng tiện lợi GreenLife Mart

            Giờ mở cửa: 4:30 - 23:59 (mở cửa suốt năm, trừ Tết Nguyên Đán nghỉ 1 ngày)
            Địa chỉ: 888A Đường Nguyễn Thị Minh Khai, Phường 5, Quận 3, TP.HCM
            Hotline: 0909 456 123
            Email: support@greenlifemart.vn
            Website: www.greenlifemart.vn
            Fanpage: facebook.com/greenlifemart.vn
            Ứng dụng di động: GreenLife Mart (trên App Store và Google Play)

            Giới thiệu:
            GreenLife Mart là chuỗi cửa hàng tiện lợi theo định hướng “Sống xanh – Mua sắm xanh”, chuyên cung cấp sản phẩm an toàn, thân thiện môi trường và đáp ứng nhu cầu tiêu dùng nhanh tại đô thị.
            Thành lập từ năm 2016, hiện GreenLife Mart có hơn 120 chi nhánh trên toàn quốc.

            Sản phẩm:
            - Đồ ăn nhanh: Bánh bao, cơm rang, salad, mì trộn, sushi gói sẵn
            - Đồ uống: Trà sữa matcha, cà phê cold brew, nước ép detox, soda trái cây
            - Thực phẩm tươi sống: Thịt bò Úc, cá saba Nhật, tôm càng xanh, rau hữu cơ Đà Lạt
            - Hàng tiêu dùng: Bột giặt, nước xả vải, nước rửa chén sinh học, giấy vệ sinh tái chế
            - Mỹ phẩm: Sữa tắm organic, dầu gội thiên nhiên, kem chống nắng không cồn

            Dịch vụ:
            - Giao hàng tận nơi trong bán kính 10km (miễn phí cho đơn từ 200.000đ)
            - Thanh toán: Tiền mặt, thẻ ngân hàng, ví điện tử (Momo, ZaloPay, VNPay)
            - Combo văn phòng trưa giao nhanh 15 phút

            Chương trình khuyến mãi:
            - Giảm 15% trong tuần sinh nhật khách hàng
            - “Giờ vàng 11h - 13h” giảm giá 10% toàn bộ đồ ăn nhanh
            - “Thứ Ba Xanh” – mua sản phẩm bao bì giấy giảm thêm 5%
            """)
        print(f"Đã tạo file mẫu: {sample_file}")

    # Run ingestion
    ingestion.run_ingestion(data_folder)


if __name__ == "__main__":
    main()
