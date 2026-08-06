from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
import requests

app = Flask(__name__)
# Настройки базы данных (SQLite создастся автоматически в папке с проектом)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SECRET_KEY'] = 'super-secret-key-123' 
db = SQLAlchemy(app)

# ==========================================
# 1. СТРУКТУРА БАЗЫ ДАННЫХ (ТАБЛИЦЫ)
# ==========================================

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.String(50), nullable=True)
    
    def __str__(self):
        return self.title

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    contact = db.Column(db.String(100))
    product_name = db.Column(db.String(150))
    date = db.Column(db.DateTime, default=db.func.now())

class SiteSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Режимы: 'lead_form' (клиент оставляет данные) или 'direct_tg' (переход в вашу телегу)
    sale_mode = db.Column(db.String(50), default='lead_form') 
    admin_tg_username = db.Column(db.String(100), default='@ваша_телега')
    telegram_bot_token = db.Column(db.String(200), default='ТОКЕН_ОТ_BOTFATHER')
    telegram_chat_id = db.Column(db.String(100), default='ВАШ_ID')

# ==========================================
# 2. НАСТРОЙКА АДМИНКИ (FLASK-ADMIN)
# ==========================================

admin = Admin(app, name='Админка: ДефектологPro', template_mode='bootstrap4')
admin.add_view(ModelView(Product, db.session, name='Управление Товарами'))
admin.add_view(ModelView(Lead, db.session, name='Заявки (Лиды)'))
admin.add_view(ModelView(SiteSettings, db.session, name='Настройки Сайта'))

# ==========================================
# 3. API ДЛЯ ФРОНТЕНДА (САЙТА)
# ==========================================

@app.route('/api/get_settings', methods=['GET'])
def get_settings():
    """Сайт запрашивает этот роут, чтобы понять, какой режим включен"""
    settings = SiteSettings.query.first()
    return jsonify({
        "mode": settings.sale_mode,
        "direct_link": f"https://t.me/{settings.admin_tg_username.replace('@', '')}"
    })

@app.route('/api/new_order', methods=['POST'])
def new_order():
    """Сюда прилетают данные из модального окна сайта"""
    data = request.json
    
    # 1. Сохраняем заявку в базу (в админку)
    lead = Lead(name=data.get('name'), contact=data.get('contact'), product_name=data.get('product'))
    db.session.add(lead)
    db.session.commit()
    
    # 2. Отправляем уведомление вам в Telegram
    settings = SiteSettings.query.first()
    if settings and settings.telegram_bot_token != 'ТОКЕН_ОТ_BOTFATHER':
        msg = f"🚨 НОВЫЙ ЗАКАЗ!\n👤 Имя: {data.get('name')}\n📞 Контакт: {data.get('contact')}\n📦 Товар: {data.get('product')}"
        tg_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        requests.post(tg_url, json={"chat_id": settings.telegram_chat_id, "text": msg})
        
    return jsonify({"status": "success", "message": "Заявка принята"})

# ==========================================
# 4. ЗАПУСК
# ==========================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Создает файл site.db при первом запуске
        if not SiteSettings.query.first():
            db.session.add(SiteSettings()) # Создает базовые настройки
            db.session.commit()
            
    app.run(debug=True, port=5000)