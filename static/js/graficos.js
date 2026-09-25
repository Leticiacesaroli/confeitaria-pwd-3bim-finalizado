window.onload = carregarGrafico;

function carregarGrafico() {
    fetch('/api/produtos_mais_comprados')
        .then(response => response.json())
        .then(dados => {

            const canvas = document.getElementById('graficoProdutos');

            if (!canvas) {
                return;
            }

            const ctx = canvas.getContext('2d');

            new Chart(ctx, {
                type: 'doughnut',

                data: {
                    labels: Object.keys(dados),

                    datasets: [{
                        label: 'Produtos mais comprados',
                        data: Object.values(dados),

                        backgroundColor: [
                            '#E8A7A1',
                            '#F4C2C2',
                            '#D8B4E2',
                            '#C084C8',
                            '#9B5DE5'
                        ],

                        borderColor: [
                            '#E8A7A1',
                            '#F4C2C2',
                            '#D8B4E2',
                            '#C084C8',
                            '#9B5DE5'
                        ],

                        borderWidth: 1
                    }]
                },

                options: {
                    responsive: true,

                    plugins: {
                        legend: {
                            position: 'bottom'
                        }
                    }
                }
            });
        })
        .catch(error => {
            console.error(
                "Erro ao carregar gráfico de produtos:",
                error
            );
        });
}