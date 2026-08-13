from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.base import BaseView, expose
from flask_admin.contrib.sqla import ModelView
from wtforms import FileField, StringField
from werkzeug.utils import secure_filename
import os
import requests

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
# Настройки базы данных (SQLite создастся автоматически в папке с проектом)
database_url = os.environ.get('DATABASE_URL')
if database_url:
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
else:
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    database_url = f"sqlite:///{os.path.join(INSTANCE_DIR, 'site.db')}"
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-change-me')
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
db = SQLAlchemy(app)

# ==========================================
# 1. СТРУКТУРА БАЗЫ ДАННЫХ (ТАБЛИЦЫ)
# ==========================================

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # type: 'workbooks' или 'courses'
    product_type = db.Column(db.String(50), nullable=False)
    
    def __str__(self):
        return self.name

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.String(50), nullable=True)
    type = db.Column(db.String(50), nullable=False)  # 'workbooks' или 'courses'
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    show_contacts = db.Column(db.Boolean, default=False)  # показывать контакты или форму
    file_path = db.Column(db.String(200), nullable=True)  # путь к файлу для скачивания
    
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
    # Контакты для отображения на сайте
    phone = db.Column(db.String(50), default='+7 (000) 000-00-00')
    email = db.Column(db.String(100), default='info@example.com')
    tg_username = db.Column(db.String(100), default='@ваша_телега')
    tg_link = db.Column(db.String(200), default='https://t.me/your_username')

# ==========================================
# 2. НАСТРОЙКА АДМИНКИ (FLASK-ADMIN)
# ==========================================

class InstructionsView(BaseView):
    @expose('/')
    def index(self):
        return self.render('admin/instructions.html')

class CategoryView(ModelView):
    column_list = ('id', 'name', 'product_type')
    form_columns = ('name', 'product_type')
    column_searchable_list = ('name',)

class ProductView(ModelView):
    column_list = ('id', 'title', 'type', 'category_id', 'show_contacts', 'price', 'file_path')
    form_columns = ('title', 'description', 'price', 'type', 'category_id', 'show_contacts', 'file_path')
    column_searchable_list = ('title',)
    column_filters = ('type', 'show_contacts')
    form_extra_fields = {
        'file': FileField('Файл товара (PDF, ZIP, DOC)')
    }
    
    def create_form(self):
        form = super().create_form()
        form.__class__ = type('ProductForm', (form.__class__,), {'enctype': 'multipart/form-data'})
        return form
    
    def edit_form(self, obj=None):
        form = super().edit_form(obj)
        form.__class__ = type('ProductForm', (form.__class__,), {'enctype': 'multipart/form-data'})
        return form
    
    def on_model_change(self, form, product, is_created):
        """Обработка загрузки файла при создании/редактировании товара"""
        file = form.file.data
        if file and file.filename:
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                
                # Если файл уже существует — добавляем префикс
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                if os.path.exists(filepath):
                    base, ext = os.path.splitext(filename)
                    counter = 1
                    while os.path.exists(filepath):
                        filename = f"{base}_{counter}{ext}"
                        filepath = os.path.join(UPLOAD_FOLDER, filename)
                        counter += 1
                
                file.save(filepath)
                product.file_path = filename
                form.file_path.data = filename

class LeadView(ModelView):
    column_list = ('id', 'name', 'contact', 'product_name', 'date')
    form_columns = ('name', 'contact', 'product_name')
    column_searchable_list = ('name', 'contact', 'product_name')

class SiteSettingsView(ModelView):
    column_list = ('id', 'phone', 'email', 'tg_username')
    form_columns = ('sale_mode', 'admin_tg_username', 'telegram_bot_token', 'telegram_chat_id', 'phone', 'email', 'tg_username', 'tg_link')

admin = Admin(app, name='Админка: ДефектологPro')
admin.add_view(InstructionsView(name='📖 Инструкция', endpoint='instructions'))
admin.add_view(CategoryView(Category, db, name='Категории'))
admin.add_view(ProductView(Product, db, name='Управление Товарами'))
admin.add_view(LeadView(Lead, db, name='Заявки (Лиды)'))
admin.add_view(SiteSettingsView(SiteSettings, db, name='Настройки Сайта'))

# ==========================================
# 3. API ДЛЯ ФРОНТЕНДА (САЙТА)
# ==========================================

@app.route('/')
def index():
    """Отдаёт главную страницу сайта"""
    return app.send_static_file('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Отдаёт список категорий с подсчётом товаров"""
    categories = Category.query.all()
    result = []
    for cat in categories:
        count = Product.query.filter_by(category_id=cat.id, type=cat.product_type).count()
        result.append({
            'id': cat.id,
            'name': cat.name,
            'type': cat.product_type,
            'products_count': count
        })
    return jsonify(result)

@app.route('/api/products', methods=['GET'])
def get_products():
    """Отдаёт все товары"""
    products = Product.query.all()
    result = []
    for p in products:
        cat = Category.query.get(p.category_id) if p.category_id else None
        result.append({
            'id': p.id,
            'title': p.title,
            'description': p.description,
            'price': p.price,
            'type': p.type,
            'category_id': p.category_id,
            'category_name': cat.name if cat else 'Без категории',
            'show_contacts': p.show_contacts,
            'file_path': p.file_path
        })
    return jsonify(result)

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Сайт запрашивает этот роут, чтобы понять, какой режим включен"""
    settings = SiteSettings.query.first()
    if settings is None:
        return jsonify({}), 404
    return jsonify({
        "mode": settings.sale_mode,
        "direct_link": f"https://t.me/{settings.admin_tg_username.replace('@', '')}",
        "phone": settings.phone,
        "email": settings.email,
        "tg_username": settings.tg_username,
        "tg_link": settings.tg_link
    })

@app.route('/api/new_order', methods=['POST'])
def new_order():
    """Сюда прилетают данные из модального окна сайта"""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    contact = (data.get('contact') or '').strip()
    product = (data.get('product') or '').strip()
    if not name or not contact or not product:
        return jsonify({"status": "error", "message": "Заполните имя, контакт и материал."}), 400
    
    # 1. Сохраняем заявку в базу (в админку)
    lead = Lead(name=name, contact=contact, product_name=product)
    db.session.add(lead)
    db.session.commit()
    
    # 2. Отправляем уведомление вам в Telegram
    settings = SiteSettings.query.first()
    if settings and settings.telegram_bot_token and settings.telegram_chat_id and settings.telegram_bot_token != 'ТОКЕН_ОТ_BOTFATHER':
        msg = f"🚨 НОВЫЙ ЗАКАЗ!\n👤 Имя: {data.get('name')}\n📞 Контакт: {data.get('contact')}\n📦 Товар: {data.get('product')}"
        tg_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        try:
            requests.post(tg_url, json={"chat_id": settings.telegram_chat_id, "text": msg}, timeout=10)
        except requests.RequestException:
            app.logger.exception('Telegram notification failed')
        
    return jsonify({"status": "success", "message": "Заявка принята"})

# ==========================================
# 4. РАЗДАЧА ФАЙЛОВ ИЗ uploads/
# ==========================================

ALLOWED_EXTENSIONS = {'pdf', 'zip', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ==========================================
# 5. ЗАПУСК
# ==========================================

# Инициализация БД при запуске (работает и локально, и на Render)
with app.app_context():
    db.create_all()
    if not SiteSettings.query.first():
        db.session.add(SiteSettings())
        db.session.commit()
    
    # Начальные категории, если их нет
    if Category.query.count() == 0:
        db.session.add_all([
            Category(name='Диагностика', product_type='diagnostics'),
            Category(name='Дефектологам', product_type='courses'),
            Category(name='Логопедам', product_type='courses'),
            Category(name='Дидактические игры', product_type='didactic_games'),
            Category(name='Документы', product_type='documents'),
            Category(name='Рабочие листы', product_type='worksheets'),
        ])
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
