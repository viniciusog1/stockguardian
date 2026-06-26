"""Popula o banco com dados iniciais (idempotente).

Cria o superusuário admin (a partir do .env) e alguns fornecedores/produtos de
demonstração. Rode com: ``python -m scripts.seed`` (com o DB no ar).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.repositories.product import ProductRepository
from app.repositories.supplier import SupplierRepository
from app.repositories.user import UserRepository

logger = get_logger("seed")


async def seed() -> None:
    async with async_session_factory() as session:
        users = UserRepository(session)
        suppliers = SupplierRepository(session)
        products = ProductRepository(session)

        # --- Admin ---
        if await users.get_by_email(settings.FIRST_SUPERUSER_EMAIL) is None:
            admin = User(
                email=settings.FIRST_SUPERUSER_EMAIL,
                hashed_password=hash_password(settings.FIRST_SUPERUSER_PASSWORD),
                full_name="Administrador",
                role=UserRole.ADMIN,
            )
            await users.add(admin)
            logger.info("seed_admin_created", email=admin.email)
        else:
            logger.info("seed_admin_exists", email=settings.FIRST_SUPERUSER_EMAIL)

        # --- Fornecedor demo ---
        demo_doc = "12345678000199"
        supplier = await suppliers.get_by_document(demo_doc)
        if supplier is None:
            supplier = Supplier(
                name="Distribuidora Exemplo Ltda",
                document=demo_doc,
                email="contato@exemplo.com",
                phone="11999990000",
            )
            await suppliers.add(supplier)
            logger.info("seed_supplier_created", document=demo_doc)

        # --- Produtos demo ---
        demo_products = [
            ("SKU-001", "Caneta Azul", Decimal("2.50"), 50, 500),
            ("SKU-002", "Caderno 96 folhas", Decimal("18.90"), 20, 200),
            ("SKU-003", "Mochila Escolar", Decimal("129.90"), 5, 50),
        ]
        for sku, name, price, min_s, max_s in demo_products:
            if await products.get_by_sku(sku) is None:
                await products.add(
                    Product(
                        sku=sku,
                        name=name,
                        unit_price=price,
                        min_stock=min_s,
                        max_stock=max_s,
                        supplier_id=supplier.id,
                    )
                )
                logger.info("seed_product_created", sku=sku)

        await session.commit()
    logger.info("seed_done")


def main() -> None:
    configure_logging()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
