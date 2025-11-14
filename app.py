import os
from datetime import datetime, time, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from sqlalchemy import func
from dotenv import load_dotenv
import secrets # NOVO: Para gerar chaves de API seguras

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# --- Configuração do Aplicativo Flask ---
app = Flask(__name__)

# Configurações de segurança e banco de dados
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '20ctIDB09')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://opalasystems_user:20ctIDB09@localhost:5432/opalasystems_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializa extensões
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
migrate = Migrate(app, db)

# --- Modelos de Banco de Dados ---
class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(128), nullable=False)
    # NOVO CAMPO: Chave de API para ESP32
    esp32_api_key = db.Column(db.String(64), unique=True, nullable=True) # Chave para autenticação da ESP32

    def set_password(self, password):
        self.senha_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.senha_hash, password)

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def __repr__(self):
        return f"Usuario('{self.nome}', '{self.email}')"

class Horario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hora = db.Column(db.Time, nullable=False)
    duracao = db.Column(db.Integer, nullable=False)
    dias_semana = db.Column(db.String(50), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    usuario = db.relationship('Usuario', backref=db.backref('horarios', lazy=True))

    def __repr__(self):
        return f"Horario('{self.hora}', '{self.duracao}', '{self.dias_semana}', '{self.ativo}')"

# --- Funções de Suporte do Flask-Login ---
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))

# --- Rotas da Aplicação ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        password = request.form.get('senha')
        confirm_password = request.form.get('confirmar_senha')
        invite_code_submitted = request.form.get('codigo')

        if not nome or not email or not password or not confirm_password or not invite_code_submitted:
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('register.html', nome=nome, email=email, codigo=invite_code_submitted)

        expected_invite_code = os.getenv('CODIGO_CONVITE')

        if not expected_invite_code or invite_code_submitted != expected_invite_code:
            flash('Código de convite inválido.', 'danger')
            return render_template('register.html', nome=nome, email=email, codigo=invite_code_submitted)

        if password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            return render_template('register.html', nome=nome, email=email, codigo=invite_code_submitted)

        existing_user = Usuario.query.filter_by(email=email).first()
        if existing_user:
            flash('Este e-mail já está cadastrado. Por favor, use outro.', 'danger')
            return render_template('register.html', nome=nome, email=email, codigo=invite_code_submitted)

        new_user = Usuario(nome=nome, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Sua conta foi criada com sucesso! Faça login para continuar.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if not email or not password:
            flash('Por favor, preencha o e-mail e a senha.', 'danger')
            return render_template('login.html')
        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and usuario.check_password(password):
            login_user(usuario)
            flash(f'Bem-vindo(a), {usuario.nome}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Login inválido. Verifique seu e-mail e senha.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado com sucesso.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    total_duracao_minutos = db.session.query(func.sum(Horario.duracao)).filter_by(
        usuario_id=current_user.id,
        ativo=True
    ).scalar()
    total_duracao_minutos = total_duracao_minutos if total_duracao_minutos is not None else 0
    horarios_ativos = Horario.query.filter_by(usuario_id=current_user.id, ativo=True).order_by(Horario.hora).all()
    return render_template('dashboard.html', 
                            duracao=total_duracao_minutos,
                            horarios_ativos=horarios_ativos)

@app.route('/horarios')
@login_required
def horarios():
    horarios_do_usuario = Horario.query.filter_by(usuario_id=current_user.id).order_by(Horario.hora).all()
    return render_template('horarios.html', horarios=horarios_do_usuario)

@app.route('/adicionar_horario', methods=['POST'])
@login_required
def adicionar_horario():
    data = request.get_json()
    if not data:
        return jsonify({'sucesso': False, 'erro': 'Dados inválidos.'}), 400
    try:
        hora_str = data.get('hora')
        duracao = data.get('duracao')
        dias_semana = data.get('dias')
        if not hora_str or not duracao or not dias_semana:
            return jsonify({'sucesso': False, 'erro': 'Todos os campos são obrigatórios.'}), 400
        hora = datetime.strptime(hora_str, '%H:%M').time()
        duracao = int(duracao)
        novo_horario = Horario(
            hora=hora,
            duracao=duracao,
            dias_semana=dias_semana,
            ativo=True,
            usuario_id=current_user.id
        )
        db.session.add(novo_horario)
        db.session.commit()
        flash('Horário de rega adicionado com sucesso!', 'success')
        return jsonify({'sucesso': True})
    except ValueError:
        db.session.rollback()
        return jsonify({'sucesso': False, 'erro': 'Formato de hora ou duração inválido.'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'sucesso': False, 'erro': f'Ocorreu um erro: {str(e)}'}), 500

@app.route('/editar_horario/<int:horario_id>', methods=['GET', 'POST'])
@login_required
def editar_horario(horario_id):
    horario = db.session.get(Horario, horario_id)
    if not horario:
        flash('Horário não encontrado.', 'danger')
        return redirect(url_for('horarios'))
    if horario.usuario_id != current_user.id:
        flash('Você não tem permissão para editar este horário.', 'danger')
        return redirect(url_for('horarios'))
    if request.method == 'POST':
        try:
            hora_str = request.form.get('hora')
            duracao = request.form.get('duracao')
            dias_semana_list = request.form.getlist('dias')
            if not hora_str or not duracao or not dias_semana_list:
                flash('Por favor, preencha todos os campos.', 'danger')
                return redirect(url_for('editar_horario', horario_id=horario.id))
            horario.hora = datetime.strptime(hora_str, '%H:%M').time()
            horario.duracao = int(duracao)
            horario.dias_semana = ",".join(dias_semana_list)
            db.session.commit()
            flash('Horário de rega atualizado com sucesso!', 'success')
            return redirect(url_for('horarios'))
        except ValueError:
            db.session.rollback()
            flash('Formato de hora ou duração inválido.', 'danger')
            return redirect(url_for('editar_horario', horario_id=horario.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Ocorreu um erro ao atualizar o horário: {str(e)}', 'danger')
            return redirect(url_for('editar_horario', horario_id=horario.id))
    dias_selecionados = horario.dias_semana.split(',')
    return render_template('editar_horario.html', horario=horario, dias_selecionados=dias_selecionados)

@app.route('/deletar_horario/<int:horario_id>', methods=['DELETE'])
@login_required
def deletar_horario(horario_id):
    horario = db.session.get(Horario, horario_id)
    if not horario:
        return jsonify({'sucesso': False, 'erro': 'Horário não encontrado.'}), 404
    if horario.usuario_id != current_user.id:
        return jsonify({'sucesso': False, 'erro': 'Você não tem permissão para deletar este horário.'}), 403
    try:
        db.session.delete(horario)
        db.session.commit()
        flash('Horário de rega excluído com sucesso!', 'success')
        return jsonify({'sucesso': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'sucesso': False, 'erro': f'Ocorreu um erro ao excluir o horário: {str(e)}'}), 500

@app.route('/ativar_horario/<int:horario_id>', methods=['PUT'])
@login_required
def ativar_horario(horario_id):
    horario = db.session.get(Horario, horario_id)
    if not horario:
        return jsonify({'sucesso': False, 'erro': 'Horário não encontrado.'}), 404
    if horario.usuario_id != current_user.id:
        return jsonify({'sucesso': False, 'erro': 'Você não tem permissão para alterar este horário.'}), 403
    data = request.get_json()
    if not data or 'ativo' not in data:
        return jsonify({'sucesso': False, 'erro': 'Dados inválidos.'}), 400
    try:
        horario.ativo = bool(data['ativo'])
        db.session.commit()
        flash(f'Horário {"ativado" if horario.ativo else "desativado"} com sucesso!', 'success')
        return jsonify({'sucesso': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'sucesso': False, 'erro': f'Ocorreu um erro ao atualizar o status: {str(e)}'}), 500

# --- NOVO ENDPOINT PARA GERAR/VISUALIZAR API KEY (para uso administrativo/do próprio usuário) ---
# ATENÇÃO: Em um ambiente de produção, esta rota deveria ser restrita a administradores
# ou ao próprio usuário logado para gerenciar sua própria chave.
@app.route('/user/<int:user_id>/manage_esp32_key', methods=['GET', 'POST'])
@login_required # Apenas usuários logados podem acessar
def manage_esp32_key(user_id):
    # Verificação de segurança: O usuário logado só pode gerenciar sua própria chave
    # Ou, se for um admin, pode gerenciar a chave de qualquer um.
    # Por simplicidade, vamos permitir que o usuário logado veja/gere sua própria chave.
    # Para gerenciar chaves de outros usuários, você precisaria de um sistema de roles (admin).
    if current_user.id != user_id:
        flash('Você não tem permissão para gerenciar a chave de API deste usuário.', 'danger')
        return redirect(url_for('dashboard'))

    user = db.session.get(Usuario, user_id)
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'generate':
            user.esp32_api_key = secrets.token_urlsafe(32) # Gera uma chave de 32 bytes (aprox. 43 caracteres)
            db.session.commit()
            flash('Nova chave de API para ESP32 gerada com sucesso!', 'success')
        elif action == 'revoke':
            user.esp32_api_key = None
            db.session.commit()
            flash('Chave de API para ESP32 revogada com sucesso!', 'info')
        return redirect(url_for('manage_esp32_key', user_id=user.id))

    return render_template('manage_esp32_key.html', user=user)


# --- ENDPOINT DA ESP32 (AGORA AUTENTICADO POR API KEY) ---
@app.route('/api/esp32/status_rega', methods=['GET'])
def esp32_status_rega():
    # Obtém a chave de API do cabeçalho 'X-API-Key'
    api_key = request.headers.get('X-API-Key')

    if not api_key:
        app.logger.warning("Tentativa de acesso ao endpoint ESP32 sem API Key.")
        return jsonify({'regar': False, 'error': 'API Key ausente.'}), 401 # Unauthorized

    # Procura o usuário pela chave de API
    user = Usuario.query.filter_by(esp32_api_key=api_key).first()

    if not user:
        app.logger.warning(f"Tentativa de acesso ao endpoint ESP32 com API Key inválida: {api_key[:5]}...")
        return jsonify({'regar': False, 'error': 'API Key inválida.'}), 401 # Unauthorized

    # Usar o horário UTC para evitar problemas de fuso horário entre servidor e ESP32
    current_utc_time = datetime.utcnow()
    current_day_of_week = current_utc_time.strftime('%a') # Ex: 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'

    # Consulta todos os horários ativos para o usuário encontrado pela API Key
    active_schedules = Horario.query.filter_by(
        usuario_id=user.id, # Usa o ID do usuário autenticado pela API Key
        ativo=True
    ).all()

    should_water = False
    for schedule in active_schedules:
        scheduled_days = schedule.dias_semana.split(',')
        # Mapeia os dias da semana para o formato 'Mon', 'Tue', etc.
        # O formato no banco de dados é "Seg,Ter,Qua", então precisamos mapear
        # Ou, idealmente, armazenar no banco de dados já no formato 'Mon', 'Tue'
        # Por enquanto, vamos fazer um mapeamento simples para o português
        day_map = {
            'Seg': 'Mon', 'Ter': 'Tue', 'Qua': 'Wed', 'Qui': 'Thu', 
            'Sex': 'Fri', 'Sab': 'Sat', 'Dom': 'Sun'
        }
        # Verifica se o dia atual (em inglês) está na lista de dias do horário (em português)
        if current_day_of_week in [day_map.get(d, '') for d in scheduled_days]:
            dummy_date = current_utc_time.date()

            schedule_start_dt = datetime.combine(dummy_date, schedule.hora)
            schedule_end_dt = schedule_start_dt + timedelta(minutes=schedule.duracao)

            if schedule_start_dt <= current_utc_time and current_utc_time < schedule_end_dt:
                should_water = True
                break

    return jsonify({"regar": should_water})

# --- Rotas de Placeholder ---
@app.route('/esp32_status')
@login_required
def esp32_status():
    # Esta rota pode ser usada para exibir o status da ESP32 no dashboard,
    # ou para linkar para a página de gerenciamento da chave de API.
    # Por exemplo, você pode passar a chave de API do usuário logado para o template.
    return render_template('esp32_status.html', esp32_api_key=current_user.esp32_api_key)

@app.route('/leitura_gabaritos')
@login_required
def leitura_gabaritos():
    return render_template('leitura_gabaritos.html')

@app.route('/status')
@login_required
def status():
    return jsonify({'status': 'ok', 'message': 'Sistema funcionando'})

@app.route('/api/horarios')
@login_required
def api_horarios():
    horarios_ativos = Horario.query.filter_by(usuario_id=current_user.id, ativo=True).all()
    horarios_data = []
    for h in horarios_ativos:
        horarios_data.append({
            'id': h.id,
            'hora': h.hora.strftime('%H:%M'),
            'duracao': h.duracao,
            'dias_semana': h.dias_semana.split(',')
        })
    return jsonify(horarios_data)

# --- Execução da Aplicação ---
if __name__ == '__main__':
    app.run(debug=True)
