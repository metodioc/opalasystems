from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import pytz
import os
from dotenv import load_dotenv
import re  # Importa o módulo de expressões regulares para validação de hora

# Carregar variáveis de ambiente
load_dotenv()

# Código de convite para registro controlado
CODIGO_CONVITE = os.environ.get('CODIGO_CONVITE', 'IRRIGACAO2025')
print(f"🔑 CÓDIGO DE CONVITE CARREGADO: '{CODIGO_CONVITE}'")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuração do banco de dados
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    if 'postgresql://' in database_url and '+psycopg' not in database_url:
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///irrig.db'
    print("🔗 Usando SQLite local")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = 'info'

# Fuso horário de Brasília
BRASILIA_TZ = pytz.timezone('America/Sao_Paulo')

def agora_br():
    """Retorna o horário atual em Brasília"""
    return datetime.now(BRASILIA_TZ)

# Modelos do banco de dados
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)
    criado_em = db.Column(db.DateTime, default=lambda: agora_br())
    horarios = db.relationship('HorarioRega', backref='usuario', lazy=True, cascade='all, delete-orphan')

    def set_senha(self, senha):
        self.senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')

    def check_senha(self, senha):
        return bcrypt.check_password_hash(self.senha_hash, senha)

class HorarioRega(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hora = db.Column(db.String(5), nullable=False)  # Formato "HH:MM"
    duracao = db.Column(db.Integer, default=600)  # Duração em minutos (assumindo que 600 é 10 minutos)
    dias_semana = db.Column(db.String(50), default='Seg,Sex')  # Ex: "Seg,Ter,Qua"
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=lambda: agora_br())
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    # Atualizando para usar Session.get() em vez de Query.get() para evitar aviso de depreciação
    return db.session.get(Usuario, int(user_id))

# Criar tabelas ANTES de qualquer requisição
with app.app_context():
    try:
        db.create_all()
        print(f"✅ Banco configurado! {agora_br().strftime('%d/%m/%Y %H:%M:%S')}")
    except Exception as e:
        print(f"❌ Erro ao configurar banco: {e}")

# Função auxiliar para verificar horários
def verificar_horario_rega():
    """Verifica se deve regar agora"""
    try:
        agora = agora_br()
        hora_atual = agora.strftime('%H:%M')
        dia_semana = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'][agora.weekday()]
        horarios = HorarioRega.query.filter_by(ativo=True).all()
        for h in horarios:
            if dia_semana in h.dias_semana.split(',') and h.hora == hora_atual:
                return True, h.duracao
        return False, 0
    except Exception as e:
        print(f"Erro ao verificar horário: {e}")
        return False, 0

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('password') # O nome do campo no HTML deve ser 'password'

        # Adiciona validação para campos vazios
        if not email or not senha:
            flash('Por favor, preencha todos os campos.', 'danger')
            return redirect(url_for('login'))

        # Correção anterior: Usar filter_by() em vez de filter() com argumento nomeado
        usuario = Usuario.query.filter_by(email=email).first()

        # Agora 'senha' não será None aqui, pois já verificamos acima
        if usuario and usuario.check_senha(senha): # Linha 120, agora segura
            login_user(usuario)
            flash('Login bem-sucedido!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Email ou senha incorretos.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        convite = request.form.get('convite')
        if convite != CODIGO_CONVITE:
            flash('Código de convite inválido.', 'danger')
            return render_template('register.html', title='Registro')
        if Usuario.query.filter_by(email=email).first():
            flash('Email já registrado.', 'danger')
            return render_template('register.html', title='Registro')
        usuario = Usuario(nome=nome, email=email)
        usuario.set_senha(senha)
        db.session.add(usuario)
        db.session.commit()
        flash('Registro realizado com sucesso! Faça login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Registro')

@app.route('/dashboard')
@login_required
def dashboard():
    regar, duracao = verificar_horario_rega()
    agora = agora_br()
    horarios = HorarioRega.query.filter_by(usuario_id=current_user.id).all()
    ativos = sum(1 for h in horarios if h.ativo)
    return render_template('dashboard.html',
                         title='Dashboard',
                         horario_atual=agora.strftime('%H:%M:%S - %d/%m/%Y'),
                         status='Regando' if regar else 'Aguardando',
                         duracao=duracao,
                         total_horarios=len(horarios),
                         horarios_ativos=ativos)

@app.route('/horarios')
@login_required
def horarios():
    horarios = HorarioRega.query.filter_by(usuario_id=current_user.id).all()
    return render_template('horarios.html', title='Meus Horários', horarios=horarios)

@app.route('/novo_horario', methods=['POST'])
@login_required
def novo_horario():
    try:
        dados = request.get_json()
        hora = dados['hora']
        duracao = int(dados['duracao'])
        dias = dados['dias_semana']  # Já vem como string no formato "Seg,Ter,Qua"
        if not re.match(r'^(?:2[0-3]|[01]?[0-9]):(?:[0-5]?[0-9])$', hora):
            return jsonify({'sucesso': False, 'erro': 'Formato de hora inválido. Use HH:MM'}), 400
        horario = HorarioRega(
            hora=hora,
            duracao=duracao,
            dias_semana=dias,
            usuario_id=current_user.id
        )
        db.session.add(horario)
        db.session.commit()
        return jsonify({'sucesso': True})
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao criar horário: {e}")
        return jsonify({'sucesso': False, 'erro': str(e)}), 500

@app.route('/editar_horario/<int:horario_id>', methods=['GET', 'POST'])
@login_required
def editar_horario(horario_id):
    horario = HorarioRega.query.get_or_404(horario_id)
    if horario.usuario_id != current_user.id:
        flash('Você não tem permissão para editar este horário.', 'danger')
        return redirect(url_for('horarios'))
    if request.method == 'POST':
        try:
            hora = request.form.get('hora')
            duracao = request.form.get('duracao')
            dias_semana = ','.join(request.form.getlist('dias_semana'))
            if not re.match(r'^(?:2[0-3]|[01]?[0-9]):(?:[0-5]?[0-9])$', hora):
                flash('Formato de hora inválido. Use HH:MM', 'danger')
                return render_template('editar_horario.html', title='Editar Horário', horario=horario, dias_semana_list=['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'])
            horario.hora = hora
            horario.duracao = int(duracao)
            horario.dias_semana = dias_semana if dias_semana else 'Seg'
            db.session.commit()
            flash('Horário atualizado com sucesso!', 'success')
            return redirect(url_for('horarios'))
        except ValueError:
            flash('Entrada inválida. Certifique-se de que os campos numéricos estão corretos.', 'danger')
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao atualizar horário: {e}")
            flash(f'Ocorreu um erro ao atualizar o agendamento: {e}', 'danger')
    # Se for um GET request, exibe o formulário preenchido
    # Passa a lista de dias da semana para o template
    return render_template('editar_horario.html', title='Editar Horário', horario=horario, dias_semana_list=['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'])

@app.route('/deletar_horario/<int:id>', methods=['DELETE'])
@login_required
def deletar_horario(id):
    try:
        horario = HorarioRega.query.get_or_404(id)
        if horario.usuario_id != current_user.id:
            return jsonify({'sucesso': False, 'erro': 'Não autorizado'}), 403
        db.session.delete(horario)
        db.session.commit()
        return jsonify({'sucesso': True})
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao deletar horário: {e}")
        return jsonify({'sucesso': False, 'erro': str(e)}), 500

@app.route('/ativar_horario/<int:id>', methods=['PUT'])
@login_required
def ativar_horario(id):
    try:
        horario = HorarioRega.query.get_or_404(id)
        if horario.usuario_id != current_user.id:
            return jsonify({'sucesso': False, 'erro': 'Não autorizado'}), 403
        dados = request.get_json()
        horario.ativo = dados['ativo']
        db.session.commit()
        return jsonify({'sucesso': True})
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao atualizar horário: {e}")
        return jsonify({'sucesso': False, 'erro': str(e)}), 500

@app.route('/status')
def status_api():
    regar, duracao = verificar_horario_rega()
    return jsonify({
        'regar': regar,
        'duracao': duracao,
        'timestamp': agora_br().isoformat()
    })

@app.route('/api/horarios')
@login_required  # Adiciona a exigência de login
def listar_horarios_api():
    # Agora filtra apenas os horários do usuário logado que estão ativos
    horarios = HorarioRega.query.filter_by(usuario_id=current_user.id, ativo=True).all()
    return jsonify([{
        'id': h.id,
        'hora': h.hora,
        'duracao': h.duracao,
        'dias_semana': h.dias_semana
    } for h in horarios])

# NOVA ROTA: Página de Status da ESP32
@app.route('/esp32_status')
@login_required
def esp32_status():
    return render_template('esp32_status.html', title='Status da Irrigação')

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200

# ROTA PARA LEITURA DE GABARITOS (CORRIGIDA E POSICIONADA CORRETAMENTE)
@app.route('/leitura_gabaritos')
@login_required
def leitura_gabaritos():
    return render_template('leitura_gabaritos.html', title='Leitura de Gabaritos')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
