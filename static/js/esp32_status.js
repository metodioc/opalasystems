// static/js/esp32_status.js

const diasNome = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab']; 

function formatarDataHora(isoString) {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    return date.toLocaleString('pt-BR', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
}

function atualizarStatusESP32() {
    fetch('/status')
        .then(response => response.json())
        .then(data => {
            const statusRegaElement = document.getElementById('statusRega');
            const duracaoRegaElement = document.getElementById('duracaoRega');
            const timestampStatusElement = document.getElementById('timestampStatus');

            if (data.regar) {
                statusRegaElement.innerHTML = '<span class="text-success"><i class="fas fa-check-circle me-2"></i>Regando Agora!</span>';
                duracaoRegaElement.textContent = `Duração: ${data.duracao} minutos`;
            } else {
                statusRegaElement.innerHTML = '<span class="text-info"><i class="fas fa-pause-circle me-2"></i>Aguardando Próxima Rega</span>';
                duracaoRegaElement.textContent = '';
            }
            timestampStatusElement.textContent = formatarDataHora(data.timestamp);
        })
        .catch(error => {
            console.error('Erro ao buscar status do ESP32:', error);
            document.getElementById('statusRega').innerHTML = '<span class="text-danger">Erro ao carregar status.</span>';
            document.getElementById('timestampStatus').textContent = 'N/A';
        });
}

function atualizarProximosHorarios() {
    const container = document.getElementById('proximosHorariosContainer');
    container.innerHTML = '<p class="text-muted">Carregando horários...</p>'; 

    fetch('/api/horarios')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(horarios => {
            const agora = new Date();
            const diaAtualNomeCurto = diasNome[agora.getDay()];
            const horariosDoDiaAtual = [];

            horarios.forEach(horario => {
                const diasSemanaAtivos = horario.dias_semana; 

                if (diasSemanaAtivos.includes(diaAtualNomeCurto)) {
                    const [horaStr, minutoStr] = horario.hora.split(':');
                    const dataOcorrenciaHoje = new Date(
                        agora.getFullYear(), agora.getMonth(), agora.getDate(),
                        parseInt(horaStr), parseInt(minutoStr), 0, 0
                    );

                    if (dataOcorrenciaHoje >= agora) {
                        horariosDoDiaAtual.push({
                            data: dataOcorrenciaHoje,
                            duracao: horario.duracao, 
                            horaOriginal: horario.hora,
                            diasOriginal: horario.dias_semana.join(', ') 
                        });
                    }
                }
            });

            horariosDoDiaAtual.sort((a, b) => a.data.getTime() - b.data.getTime());

            if (horariosDoDiaAtual.length === 0) {
                container.innerHTML = '<p class="text-muted">Nenhum horário futuro para hoje.</p>';
                return;
            }

            container.innerHTML = ''; // limpa antes de adicionar novos
            horariosDoDiaAtual.forEach(agendamento => {
                const horaFormatada = agendamento.data.toLocaleTimeString('pt-BR', {
                    hour: '2-digit', minute: '2-digit'
                });
                const itemDiv = document.createElement('div');
                itemDiv.className = 'd-flex justify-content-between align-items-center mb-2 pb-2 border-bottom';
                itemDiv.innerHTML = `
                    <div>
                        <strong class="text-primary">${horaFormatada}</strong>
                        <br><small class="text-muted">Duração: ${agendamento.duracao} min</small>
                    </div>
                    <span class="badge bg-secondary">${agendamento.diasOriginal}</span>
                `;
                container.appendChild(itemDiv);
            });

            // LINHA CORRIGIDA: operador lógico correto "&&"
            if (container.lastChild && container.lastChild.classList.contains('border-bottom')) {
                container.lastChild.classList.remove('border-bottom');
                container.lastChild.classList.remove('pb-2');
            }
        })
        .catch(error => {
            console.error('Erro ao buscar horários:', error);
            container.innerHTML = '<p class="text-danger">Erro ao carregar horários.</p>';
        });
}

document.addEventListener('DOMContentLoaded', () => {
    atualizarStatusESP32();
    atualizarProximosHorarios();
});
setInterval(() => {
    atualizarStatusESP32();
    atualizarProximosHorarios();
}, 5000);
