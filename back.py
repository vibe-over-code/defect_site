from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.base import BaseView, expose
from flask_admin.contrib.sqla import ModelView
from wtforms import FileField, SelectField, MultipleFileField
from werkzeug.utils import secure_filename
from sqlalchemy import text, inspect
from markupsafe import Markup, escape
from urllib.parse import quote
import os
import json
import requests

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
os.makedirs(INSTANCE_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# DATABASE_URL используется на Render/PostgreSQL, локально — SQLite.
database_url = os.environ.get('DATABASE_URL')
if database_url:
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
else:
    database_url = f"sqlite:///{os.path.join(INSTANCE_DIR, 'site.db')}"

app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-only-change-me'),
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
)

db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {'pdf', 'zip', 'doc', 'docx'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    product_type = db.Column(db.String(50), nullable=False)
    audience = db.Column(db.String(50), nullable=False, default='defectologists')
    def __str__(self):
        return self.name

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.String(50), nullable=True)
    type = db.Column(db.String(50), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    show_contacts = db.Column(db.Boolean, default=False)
    file_path = db.Column(db.String(200), nullable=True)
    image_path = db.Column(db.String(255), nullable=True)
    gallery_paths = db.Column(db.Text, nullable=True)
    def __str__(self):
        return self.title

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    contact = db.Column(db.String(100))
    product_name = db.Column(db.String(150))
    date = db.Column(db.DateTime, default=db.func.current_timestamp())

class SiteSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_mode = db.Column(db.String(50), default='lead_form')
    admin_tg_username = db.Column(db.String(100), default='@ваша_телега')
    telegram_bot_token = db.Column(db.String(200), default='')
    telegram_chat_id = db.Column(db.String(100), default='')
    phone = db.Column(db.String(50), default='+7 (000) 000-00-00')
    email = db.Column(db.String(100), default='info@example.com')
    tg_username = db.Column(db.String(100), default='@ваша_телега')
    tg_link = db.Column(db.String(200), default='https://t.me/your_username')
    hero_image_path = db.Column(db.String(255), default='hero.png')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_upload(file_storage, image=False):
    """Сохраняет загруженный файл в uploads и возвращает его имя."""
    if not file_storage or not file_storage.filename:
        return None
    checker = allowed_image if image else allowed_file
    if not checker(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    base, ext = os.path.splitext(filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    counter = 1
    while os.path.exists(filepath):
        filename = f'{base}_{counter}{ext}'
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        counter += 1
    file_storage.save(filepath)
    return filename


def ensure_schema():
    """Добавляет новые колонки в уже существующую БД без удаления старых данных."""
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'product' in tables:
        columns = {c['name'] for c in inspector.get_columns('product')}
        if 'image_path' not in columns:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE product ADD COLUMN image_path VARCHAR(255)'))
        if 'gallery_paths' not in columns:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE product ADD COLUMN gallery_paths TEXT'))
    if 'site_settings' in tables:
        columns = {c['name'] for c in inspector.get_columns('site_settings')}
        if 'hero_image_path' not in columns:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE site_settings ADD COLUMN hero_image_path VARCHAR(255)'))
    if 'category' in tables:
        columns = {c['name'] for c in inspector.get_columns('category')}
        if 'audience' not in columns:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE category ADD COLUMN audience VARCHAR(50) NOT NULL DEFAULT 'defectologists'"))


class InstructionsView(BaseView):
    @expose('/')
    def index(self):
        return self.render('admin/instructions_beginner.html')


class CategoryView(ModelView):
    column_list = ('id', 'name', 'audience')
    form_columns = ('name', 'audience', 'product_type')
    column_searchable_list = ('name',)
    column_formatters = {'audience': lambda view, context, model, name: {
        'defectologists': 'Дефектологам', 'speech_therapists': 'Логопедам',
        'school': 'Подготовка к школе'
    }.get(model.audience, model.audience)}
    form_extra_fields = {
        'audience': SelectField('Раздел меню', choices=[
            ('defectologists', 'Дефектологам'),
            ('speech_therapists', 'Логопедам'),
            ('school', 'Подготовка к школе'),
        ], default='defectologists'),
        'product_type': SelectField('Вид материала', choices=[
            ('diagnostics', 'Диагностика'), ('didactic_games', 'Дидактические игры'),
            ('courses', 'Программы коррекционных курсов'), ('documents', 'Документы'),
            ('worksheets', 'Рабочие листы'), ('workbooks', 'Рабочие тетради'),
            ('webinars', 'Вебинары'), ('school_reading', 'Чтение'),
            ('school_letters', 'Буквы и слоги'), ('school_math', 'Математический счет'),
            ('school_motor', 'Развитие графо-моторных навыков'),
            ('school_writing', 'Подготовка руки к письму'),
            ('school_diagnostics', 'Диагностика готовности к школе'),
            ('school_geometry', 'Геометрический материал'),
        ], default='documents')
    }


class ProductView(ModelView):
    column_list = ('id', 'title', 'price', 'show_contacts', 'image_path')
    form_columns = ('title', 'description', 'price', 'type', 'category_id', 'show_contacts', 'image', 'file')
    column_searchable_list = ('title',)
    column_filters = ('type', 'show_contacts')
    column_formatters = {
        'image_path': lambda view, context, model, name: Markup(
            f'<div style="border:3px solid #2d9c9a;border-radius:10px;padding:3px;width:74px;text-align:center">'
            f'<img src="/uploads/{escape(quote(model.image_path))}" style="width:64px;height:48px;object-fit:cover;border-radius:6px;display:block">'
            f'<small style="color:#23817f;font-weight:700">ПРЕВЬЮ</small></div>'
        ) if model.image_path else Markup('<span style="color:#999">Нет обложки</span>')
    }
    form_args = {
        'title': {'label': 'Название материала'},
        'description': {'label': 'Короткое описание'},
        'price': {'label': 'Цена'},
        'category_id': {'label': 'Категория'},
        'show_contacts': {'label': 'Показывать контакты'},
    }
    form_extra_fields = {
        'type': SelectField('Вид материала', choices=[
            ('diagnostics', 'Диагностика'), ('didactic_games', 'Дидактические игры'),
            ('courses', 'Программы коррекционных курсов'), ('documents', 'Документы'),
            ('worksheets', 'Рабочие листы'), ('workbooks', 'Рабочие тетради'),
            ('webinars', 'Вебинары'), ('school_reading', 'Чтение'),
            ('school_letters', 'Буквы и слоги'), ('school_math', 'Математический счет'),
            ('school_motor', 'Развитие графо-моторных навыков'),
            ('school_writing', 'Подготовка руки к письму'),
            ('school_diagnostics', 'Диагностика готовности к школе'),
            ('school_geometry', 'Геометрический материал'),
        ]),
        'category_id': SelectField('Категория', coerce=int),
        'image': FileField('🟩 ПРЕВЬЮ: главная картинка карточки (PNG/JPG/WEBP)'),
        'gallery': MultipleFileField('Остальные картинки (можно выбрать несколько)', render_kw={'multiple': True}),
        'file': FileField('Файл товара (PDF, ZIP, DOC)')
    }

    @staticmethod
    def _category_choices():
        audience_names = {
            'defectologists': 'Дефектологам',
            'speech_therapists': 'Логопедам',
            'school': 'Подготовка к школе',
        }
        categories = Category.query.order_by(Category.audience, Category.name).all()
        return [(category.id, f"{audience_names.get(category.audience, 'Раздел')}: {category.name}")
                for category in categories]

    def create_form(self):
        form = super().create_form()
        form.category_id.choices = self._category_choices()
        form.__class__ = type('ProductForm', (form.__class__,), {'enctype': 'multipart/form-data'})
        return form

    def edit_form(self, obj=None):
        form = super().edit_form(obj)
        form.category_id.choices = self._category_choices()
        form.__class__ = type('ProductForm', (form.__class__,), {'enctype': 'multipart/form-data'})
        return form

    def on_model_change(self, form, product, is_created):
        """Сохраняет изображение карточки и файл товара."""
        image = getattr(form, 'image', None)
        if image and image.data and image.data.filename:
            filename = save_upload(image.data, image=True)
            if not filename:
                raise ValueError('Изображение должно быть PNG, JPG, JPEG или WEBP.')
            product.image_path = filename

        gallery_field = getattr(form, 'gallery', None)
        if gallery_field and gallery_field.data:
            gallery = []
            for image_file in gallery_field.data:
                filename = save_upload(image_file, image=True)
                if filename:
                    gallery.append(filename)
            old_gallery = json.loads(product.gallery_paths or '[]')
            product.gallery_paths = json.dumps(old_gallery + gallery, ensure_ascii=False)

        file_field = getattr(form, 'file', None)
        if file_field and file_field.data and file_field.data.filename:
            filename = save_upload(file_field.data, image=False)
            if not filename:
                raise ValueError('Файл товара должен быть PDF, ZIP, DOC или DOCX.')
            product.file_path = filename


class LeadView(ModelView):
    column_list = ('id', 'name', 'contact', 'product_name', 'date')
    form_columns = ('name', 'contact', 'product_name')
    column_searchable_list = ('name', 'contact', 'product_name')


class SiteSettingsView(ModelView):
    form_columns = ('sale_mode', 'admin_tg_username', 'telegram_bot_token', 'telegram_chat_id', 'phone', 'email', 'tg_username', 'tg_link', 'hero_image')
    column_list = ('id', 'phone', 'email', 'tg_username', 'hero_image_path')
    form_extra_fields = {'hero_image': FileField('Картинка большой шапки (PNG/JPG/WEBP)')}
    can_create = False
    can_delete = False

    def edit_form(self, obj=None):
        form = super().edit_form(obj)
        form.__class__ = type('SiteSettingsForm', (form.__class__,), {'enctype': 'multipart/form-data'})
        return form

    def on_model_change(self, form, settings, is_created):
        image = getattr(form, 'hero_image', None)
        if image and image.data and image.data.filename:
            filename = save_upload(image.data, image=True)
            if not filename:
                raise ValueError('Картинка должна быть PNG, JPG, JPEG или WEBP.')
            settings.hero_image_path = filename


admin = Admin(app, name='Админка: Материалы для занятий')
admin.add_view(InstructionsView(name='📖 С чего начать', endpoint='instructions'))
admin.add_view(CategoryView(Category, db, name='🗂 Категории'))
admin.add_view(ProductView(Product, db, name='🛒 Материалы'))
admin.add_view(LeadView(Lead, db, name='📥 Заявки'))
admin.add_view(SiteSettingsView(SiteSettings, db, name='⚙️ Сайт и контакты'))


@app.route('/')
def index():
    """Отдаёт главную страницу сайта."""
    return render_template('index.html')


@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Возвращает категории с количеством товаров."""
    categories = Category.query.order_by(Category.id).all()
    result = []
    for cat in categories:
        count = Product.query.filter_by(category_id=cat.id, type=cat.product_type).count()
        result.append({'id': cat.id, 'name': cat.name, 'audience': cat.audience,
                       'type': cat.product_type, 'products_count': count})
    return jsonify(result)


@app.route('/api/products', methods=['GET'])
def get_products():
    """Возвращает товары каталога вместе с изображением карточки."""
    products = Product.query.order_by(Product.id.desc()).all()
    result = []
    for p in products:
        cat = db.session.get(Category, p.category_id) if p.category_id else None
        result.append({
            'id': p.id, 'title': p.title, 'description': p.description,
            'price': p.price, 'type': p.type, 'category_id': p.category_id,
            'audience': cat.audience if cat else 'defectologists',
            'category_name': cat.name if cat else 'Без категории',
            'show_contacts': p.show_contacts, 'file_path': p.file_path,
            'image_path': p.image_path,
            'gallery_paths': json.loads(p.gallery_paths or '[]')
        })
    return jsonify(result)


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Возвращает публичные настройки сайта."""
    settings = SiteSettings.query.first()
    if settings is None:
        return jsonify({}), 404
    return jsonify({
        'mode': settings.sale_mode,
        'direct_link': f"https://t.me/{settings.admin_tg_username.replace('@', '')}",
        'phone': settings.phone,
        'email': settings.email,
        'tg_username': settings.tg_username,
        'tg_link': settings.tg_link,
        'hero_image_path': settings.hero_image_path
    })


@app.route('/api/new_order', methods=['POST'])
def new_order():
    """Принимает заявку, сохраняет её в БД и отправляет уведомление в Telegram."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    contact = (data.get('contact') or '').strip()
    product = (data.get('product') or '').strip()
    if not name or not contact or not product:
        return jsonify({'status': 'error', 'message': 'Заполните имя, контакт и материал.'}), 400

    lead = Lead(name=name, contact=contact, product_name=product)
    db.session.add(lead)
    db.session.commit()

    settings = SiteSettings.query.first()
    if settings and settings.telegram_bot_token and settings.telegram_chat_id and settings.telegram_bot_token != 'ТОКЕН_ОТ_BOTFATHER':
        msg = f"🚨 НОВЫЙ ЗАКАЗ!\n👤 Имя: {name}\n📞 Контакт: {contact}\n📦 Товар: {product}"
        tg_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        try:
            requests.post(tg_url, json={'chat_id': settings.telegram_chat_id, 'text': msg}, timeout=10)
        except requests.RequestException:
            app.logger.exception('Telegram notification failed')

    return jsonify({'status': 'success', 'message': 'Заявка принята'})


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Отдаёт загруженные изображения и файлы товаров."""
    return send_from_directory(UPLOAD_FOLDER, filename)


with app.app_context():
    db.create_all()
    ensure_schema()
    if not SiteSettings.query.first():
        db.session.add(SiteSettings(hero_image_path='hero.png'))
        db.session.commit()
    if Category.query.count() == 0:
        db.session.add_all([
            Category(name='Диагностика', product_type='diagnostics'),
            Category(name='Дефектологам', product_type='courses'),
            Category(name='Логопедам', product_type='courses'),
            Category(name='Дидактические игры', product_type='didactic_games'),
            Category(name='Документы', product_type='documents'),
            Category(name='Рабочие листы', product_type='worksheets'),
            Category(name='Подготовка к школе', product_type='school'),
        ])
        db.session.commit()

    default_categories = [
        ('Дефектологам', 'Диагностика', 'diagnostics'),
        ('Дефектологам', 'Дидактические игры', 'didactic_games'),
        ('Дефектологам', 'Рабочие тетради', 'workbooks'),
        ('Дефектологам', 'Рабочие листы', 'worksheets'),
        ('Дефектологам', 'Документы Дефектолога', 'documents'),
        ('Дефектологам', 'Программы коррекционных курсов', 'courses'),
        ('Дефектологам', 'Вебинары', 'webinars'),
        ('Логопедам', 'Диагностика', 'diagnostics'),
        ('Логопедам', 'Дидактические игры', 'didactic_games'),
        ('Логопедам', 'Документы Логопеда', 'documents'),
        ('Логопедам', 'Программы коррекционных курсов', 'courses'),
        ('Логопедам', 'Рабочие листы', 'worksheets'),
        ('Подготовка к школе', 'Чтение', 'school_reading'),
        ('Подготовка к школе', 'Буквы и слоги', 'school_letters'),
        ('Подготовка к школе', 'Математический счет', 'school_math'),
        ('Подготовка к школе', 'Развитие графо-моторных навыков', 'school_motor'),
        ('Подготовка к школе', 'Подготовка руки к письму', 'school_writing'),
        ('Подготовка к школе', 'Диагностика готовности к школе', 'school_diagnostics'),
        ('Подготовка к школе', 'Геометрический материал', 'school_geometry'),
    ]
    legacy_audiences = {'Дефектологам': 'defectologists', 'Логопедам': 'speech_therapists',
                        'Подготовка к школе': 'school'}
    for legacy_name, legacy_audience in legacy_audiences.items():
        for legacy_category in Category.query.filter_by(name=legacy_name).all():
            legacy_category.audience = legacy_audience
    canonical_names = {
        ('defectologists', 'документы дефектолога'): 'Документы Дефектолога',
        ('speech_therapists', 'документы логопеда'): 'Документы Логопеда',
        ('school', 'математический счёт'): 'Математический счет',
    }
    for category in Category.query.all():
        canonical = canonical_names.get((category.audience, category.name.lower()))
        if canonical:
            category.name = canonical
    for audience_name, category_name, product_type in default_categories:
        audience = {'Дефектологам': 'defectologists', 'Логопедам': 'speech_therapists',
                    'Подготовка к школе': 'school'}[audience_name]
        exists = Category.query.filter_by(name=category_name, audience=audience).first()
        if not exists:
            db.session.add(Category(name=category_name, product_type=product_type, audience=audience))
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
