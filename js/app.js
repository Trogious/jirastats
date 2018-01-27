
// DataLoader ----------------------------------------------------------------------------
const DataLoader = function() {

  this.onLoadListeners = [];
  this.rawData = null;

  this.load = function(url, onComplete) {
    var self = this;
    $.getJSON('data.json', function(data) {
      self.rawData = data;
      for(var i in self.onLoadListeners) {
        self.onLoadListeners[i]();
      }
    });
  };

  this.onLoad = function(callback) {
    this.onLoadListeners.push(callback);
  };

  this.getChartCount = function() {
    return this.rawData ? this.rawData.projects.length : 0;
  }

  this.getChartData = function(index) {
    if(index >= this.getChartCount()) throw "No chart data for index " + index;
    return this.rawData.projects[index];
  }
}

// ProjectRenderer --------------------------------------------------------------------
const ProjectRenderer = function(data) {
  this.data = data;

  this.render = function($container) {
    $template = $(
      '<hr/>' +
      '<div class="row">' +
        '<div class="col-12 title-container"></div>' +
      '</div>' +
      '<div class="row">' +
        '<div class="col-md-4 col-sm-6 stats-container" style="height: 300px"></div>' +
        '<div class="col-md-8 col-sm-6 burnup-container" style="height: 300px"></div>' +
      '</div>'
    );
    $title = $('<h1></h1>');
    $burnUp = $('<canvas />');
    $stats = $('<canvas />');


    this.renderTitle($title);
    this.renderBurnUp($burnUp);
    this.renderScopeStats($stats);

    $container.append($template);
    $template.find(".title-container").append($title);
    $template.find(".stats-container").append($stats);
    $template.find(".burnup-container").append($burnUp);
  }

  this.renderTitle = function($container) {
    $container.html("Project Key: " + this.data.project_key);
  }

  this.renderScopeStats = function($container) {
    var ctx = $container.get(0).getContext('2d');
    var totalScope = this.data.total_scope_estimate;
    var burnedScope = this.data.burned_scope_estimate;
    var velocity = this.data.average_velocity;

    var chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ["Total Scope", "Burned Scope", "Avg. Sprint Velocity"],
        datasets: [
          {
            backgroundColor: [
              'rgb(99, 99, 240)',
              'rgb(99, 240, 99)',
              'rgb(240, 99, 99)'
            ],
            data: [
              totalScope,
              burnedScope,
              velocity
            ]
          }
        ]
      },
      options: {
        maintainAspectRatio: false,
        legend: {
          display: false
        },
        scales: {
          yAxes: [{
            ticks: {
              min: 0,
            }
          }],
          xAxes: [{
            ticks: {
              minRotation: 90,
            }
          }]
        }
      }
    });
  }

  this.renderBurnUp = function($container) {
    var ctx = $container.get(0).getContext('2d');
    var labels = this.data.to_date.dates;
    var totalScope = this.data.to_date.total_estimates;
    var burnedScope = this.data.to_date.burned_estimates;
    var unit = this.data.estimate_type.replace('_', ' ');

    // remove future data
    var now = new Date();
    var timestamp;
    var dt;
    for(var i=labels.length-1; i >= 0; i --) {
      timestamp = new Date(labels[i]);
      var dt = timestamp.getTime() - now.getTime();
      if(dt > 0) {
        totalScope.pop();
        burnedScope.pop();
      }
    }

    // render chart
    var chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: "Total Scope",
            borderColor: 'rgb(99, 99, 240)',
            backgroundColor: 'rgba(0,0,0,0)',
            data: totalScope,
          },
          {
            label: "Burned Scope",
            borderColor: 'rgb(240, 99, 99)',
            backgroundColor: 'rgba(0,0,0,0)',
            data: burnedScope,
          }
        ]
      },
      options: {
        maintainAspectRatio: false,
        scales: {
          yAxes: [{
            scaleLabel: {
              display: true,
              labelString: unit
            }
          }]
        }
      }
    });
  }
}

// Entrypoint ------------------------------------------------------------------
var loader = new DataLoader();
loader.onLoad(function() {
  var chartCount = loader.getChartCount();
  for(var i=0; i < chartCount; i++) {
    var renderer = new ProjectRenderer(loader.getChartData(i));
    renderer.render($('#dashboard'));
    console.log("Chart #" + i + " Data", loader.getChartData(i));
  }
})
loader.load('./data.json');
