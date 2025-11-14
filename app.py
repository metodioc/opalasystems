import os
from datetime import datetime, time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate # Para gerenciar migrações de banco de dados
from sqlalchemy import func # NOVO: Importar func para funções de agregação como SUM
from dotenv import load_dotenv # NOVO: Importar load_dotenv para carregar variáveis do .env

# Carrega as variáveis de ambiente do arquivo .env
# Isso garante que SECRET_KEY, DATABASE_URL e CODIGO_CONVITE sejam lidos
load_dotenv()

# --- Configuração do Aplicativo Flask ---
app = Flask(__name__)

# Configurações de segurança e banco de dados
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sua_chave_secreta_muito_segura_aqui') # Use uma chave forte e variável de ambiente em produção
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://opalasystems_user:sua_senha_forte_aqui@localhost:5432/opalasystems_db') # Exemplo para PostgreSQL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializa extensões
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' # Define a rota para onde o usuário será redirecionado se tentar acessar uma página protegida sem estar logado
login_manager.login_message_category = 'info' # Categoria da mensagem flash para login_required
migrate = Migrate(app, db) # Inicializa o Flask-Migrate

# --- Modelos de Banco de Dados ---
# Modelo de Usuário
class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(128), nullable=False) # Armazena o hash da senha

    def set_password(self, password):
        self.senha_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.senha_hash, password)

    # Métodos exigidos pelo Flask-Login
    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return True # Todos os usuários são ativos por padrão

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def __repr__(self):
        return f"Usuario('{self.nome}', '{self.email}')"

# Modelo de Horário de Rega
class Horario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hora = db.Column(db.Time, nullable=False) # Armazena apenas a hora (HH:MM)
    duracao = db.Column(db.Integer, nullable=False) # Duração em minutos
    dias_semana = db.Column(db.String(50), nullable=False) # Ex: "Seg,Ter,Qua"
    ativo = db.Column(db.Boolean, default=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    # Relacionamento com o modelo Usuario
    usuario = db.relationship('Usuario', backref=db.backref('horarios', lazy=True))

    def __repr__(self):
        return f"Horario('{self.hora}', '{self.duracao}', '{self.dias_semana}', '{self.ativo}')"

# --- Funções de Suporte do Flask-Login ---
@login_manager.user_loader
def load_user(user_id):
    # CORREÇÃO: Usando db.session.get() para compatibilidade com SQLAlchemy 2.0
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
        # CORREÇÃO AQUI: Use 'senha' e 'confirmar_senha' para corresponder ao HTML
        password = request.form.get('senha')
        confirm_password = request.form.get('confirmar_senha')

        # ADIÇÃO AQUI: Obter o código de convite do formulário
        invite_code_submitted = request.form.get('codigo')

        # CORREÇÃO AQUI: Incluir invite_code_submitted na validação de campos vazios
        if not nome or not email or not password or not confirm_password or not invite_code_submitted:
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('register.html', nome=nome, email=email, codigo=invite_code_submitted) # Passa os dados para manter no formulário

        # ADIÇÃO AQUI: Obter o código de convite do ambiente
        expected_invite_code = os.getenv('CODIGO_CONVITE')

        # ADIÇÃO AQUI: Validação do código de convite
        # Verifica se o código de convite está configurado e se o enviado corresponde
        if not expected_invite_code or invite_code_submitted != expected_invite_code:
            flash('Código de convite inválido.', 'danger')
            return render_template('register.html', nome=nome, email=email, codigo=invite_code_submitted) # Passa os dados para manter no formulário

        if password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            return render_template('register.html', nome=nome, email=email, codigo=invite_code_submitted) # Passa os dados para manter no formulário

        # Validação de email existente
        existing_user = Usuario.query.filter_by(email=email).first()
        if existing_user:
            flash('Este e-mail já está cadastrado. Por favor, use outro.', 'danger')
            return render_template('register.html', nome=nome, email=email, codigo=invite_code_submitted) # Passa os dados para manter no formulário

        # Se tudo estiver OK, cria o novo usuário
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
        password = request.form.get('password') # Aqui o nome 'password' está correto, pois o formulário de login deve usar 'password'
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
    # NOVO: Calcular a duração total das regas ativas para o usuário logado
    total_duracao_minutos = db.session.query(func.sum(Horario.duracao)).filter_by(
        usuario_id=current_user.id,
        ativo=True
    ).scalar()
    # Se não houver horários ativos, a soma pode retornar None, então definimos como 0
    total_duracao_minutos = total_duracao_minutos if total_duracao_minutos is not None else 0
    # Você pode querer passar também os horários ativos para exibir no dashboard
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
    horario = db.session.get(Horario, horario_id) # Usando db.session.get()
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
    horario = db.session.get(Horario, horario_id) # Usando db.session.get()
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
    horario = db.session.get(Horario, horario_id) # Usando db.session.get()
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

# --- Rotas de Placeholder (mantenha se você as tiver em outros arquivos ou precisar delas) ---
@app.route('/esp32_status')
@login_required
def esp32_status():
    return render_template('esp32_status.html')

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
    # Comentado para usar Flask-Migrate para gerenciamento de esquema
    # Se você ainda não executou 'flask db upgrade', faça-o!
    # with app.app_context():
    #     db.create_all()
    app.run(debug=True)
