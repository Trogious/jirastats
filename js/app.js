// DataLoader ----------------------------------------------------------------------------
const DataLoader = function(project_ids, dataset_ids) {
  this.onLoadListeners = [];
  this.rawData = null;
  this.projectIds = project_ids;
  this.datasetIds = dataset_ids;

  this.filterByIds = function() {
    if (this.rawData && this.projectIds.length > 0) {
      for (var p = 0; p < this.rawData.projects.length; ++p) {
        var found = false;
        for (var i in this.projectIds) {
          if (this.rawData.projects[p].project_key === this.projectIds[i]) {
            found = true;
            break;
          }
        }
        if (!found) {
          this.rawData.projects.splice(p--, 1);
        }
      }
    }
  }

  this.datasetsIncluded = function(d) {
    return this.datasetIds.includes(''+d.id);
  }.bind(this);

  this.filterByDatasetIds = function() {
    if (this.datasetIds.length > 0) {
      for (var p = 0; p < this.rawData.projects.length; ++p) {
        for (var d = 0; d < this.rawData.projects[p].datasets.length; ++d) {
          this.rawData.projects[p].datasets[d].id = d;
        }
        this.rawData.projects[p].datasets = this.rawData.projects[p].datasets.filter(this.datasetsIncluded);
      }
    }
  }

  this.load = function(url, onComplete) {
    var self = this;
    $.getJSON(url, function(data) {
      self.rawData = data;
      self.filterByIds();
      self.filterByDatasetIds();
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
  };

  this.getDatasetCount = function(index) {
    if (this.rawData) {
      return this.rawData.projects[index].datasets ? this.rawData.projects[index].datasets.length : 1;
    }

    return 0;
  };

  this.getChartData = function(index) {
    if(index >= this.getChartCount()) throw "No chart data for index " + index;
    return this.rawData.projects[index];
  };

  this.getGeneratedAt = function() {
    return this.rawData ? this.rawData.generated_at : '';
  };
}

// ProjectRenderer --------------------------------------------------------------------
const ProjectRenderer = function(data, datasetCount) {
  this.data = data;
  this.datasetCount = datasetCount;

  this.render = function($container) {
    var template_str =
      '<hr/>' +
      '<div class="row">' +
        '<div class="col-12 title-container"></div>' +
      '</div>';
    for (var i = 0; i < this.datasetCount; ++i) {
      template_str +=
        '<div class="row">' +
          '<div class="col-md-4 col-sm-6 stats-container' + i + '" style="height: 300px"></div>' +
          '<div class="col-md-8 col-sm-6 burnup-container' + i + '" style="height: 300px"></div>' +
        '</div>';
    }
    $template = $(template_str);
    $title = $('<h1></h1>');
    this.renderTitle($title);

    var statsList = [];
    var burnUpList = [];
    for (var i = 0; i < this.datasetCount; ++i) {
      $stats = $('<canvas />');
      $burnUp = $('<canvas />');
      this.renderScopeStats($stats, i);
      this.renderBurnUp($burnUp, i);
      statsList.push($stats);
      burnUpList.push($burnUp);
    }

    $container.append($template);
    $template.find(".title-container").append($title);

    for (var i = 0; i < this.datasetCount; ++i) {
      $template.find(".stats-container" + i).append(statsList[i]);
      $template.find(".burnup-container" + i).append(burnUpList[i]);
    }
  }

  this.renderTitle = function($container) {
    if (this.data.project_key === this.data.title) {
      $container.html("Project: " + this.data.project_key);
    } else {
      $container.html(this.data.title);
    }
  }

  this.renderScopeStats = function($container, id) {
    var ctx = $container.get(0).getContext('2d');
    var totalScope = this.data.datasets[id].total_scope_estimate;
    var burnedScope = this.data.datasets[id].burned_scope_estimate;
    var velocity = this.data.average_velocity;
    var unit = this.data.estimate_type.replace('_', ' ');
    var urls = [
      this.data.datasets[id].total_scope_url,
      this.data.datasets[id].burned_scope_url,
      this.data.velocity_url
    ];

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
            },
            scaleLabel: {
              display: true,
              labelString: unit
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
    $container.click(function(evt) {
        var activePoints = chart.getElementsAtEvent(evt);
        if (activePoints.length) {
          if (activePoints[0]._index < 3) {
            window.open(urls[activePoints[0]._index]);
          }
        }
    });
  }

  this.renderBurnUp = function($container, id) {
    var ctx = $container.get(0).getContext('2d');
    var dates = this.data.datasets[id].dates;
    var totalScope = this.data.datasets[id].total_estimates;
    var burnedScope = this.data.datasets[id].burned_estimates;
    var unit = this.data.estimate_type.replace('_', ' ');
    var milestones = this.data.datasets[id].milestones;
    var totalUrls = this.data.datasets[id].urls.total;
    var burnedUrls = this.data.datasets[id].urls.burned;
    var scopeName = this.data.datasets[id].name;

    // remove future data
    var now = new Date();
    var timestamp;
    var dt;
    for(var i = dates.length-1; i >= 0; --i) {
      timestamp = new Date(dates[i]);
      var dt = timestamp.getTime() - now.getTime();
      if(dt > 0) {
        totalScope.pop();
        burnedScope.pop();
      } else {
        totalScope[i] = { x: timestamp, y: totalScope[i] };
        burnedScope[i] = { x: timestamp, y: burnedScope[i] };
      }
    }

    // prepare annotations for milestones
    var annotations = [];
    var milestoneDataSets = [];
    var pos = 0;
    for (var i in milestones) {
      annotations.push({
  			type: 'line',
  			mode: 'vertical',
  			scaleID: 'x-axis-0',
  			value: new Date(milestones[i].date),
  			borderColor: milestones[i].color,
  			borderWidth: 2
      });
      milestoneDataSets.push({
        label: milestones[i].name,
        borderColor: milestones[i].color,
        backgroundColor: milestones[i].color,
        pointRadius: 5,
        pointHitRadius: 10,
        data: [{
          x: new Date(milestones[i].date),
          y: 1
        }]
      });
      pos += 20;
    }

    // render chart
    var chart = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [
          {
            label: "Total Scope",
            borderColor: 'rgb(99, 99, 240)',
            backgroundColor: 'rgba(0,0,0,0)',
            data: totalScope,
          },
          {
            label: "Burned Scope",
            borderColor: 'rgb(99, 240, 99)',
            backgroundColor: 'rgba(0,0,0,0)',
            data: burnedScope,
          }
        ].concat(milestoneDataSets)
      },
      options: {
        maintainAspectRatio: false,
        scales: {
          yAxes: [{
            type: 'linear',
            scaleLabel: {
              display: true,
              labelString: unit
            }
          }],
          xAxes: [{
            id: 'x-axis-0',
            type: 'linear',
            scaleLabel: {
              display: true,
              labelString: scopeName
            },
            ticks: {
              callback: function(value, index, values) {
                return new Date(value).toISOString().slice(0,10);
              }
            }
          }]
        },
        annotation: {
          annotations: annotations
        },
        tooltips: {
          callbacks: {
            title: function(tooltipItem, data) {
              return new Date(tooltipItem[0].xLabel).toISOString().slice(0,10);
            },
            label: function(tooltipItem, data) {
              var label = data.datasets[tooltipItem.datasetIndex].label || '';

              if (tooltipItem.datasetIndex < 2) {
                if (label) {
                  label += ': ';
                }
                label += tooltipItem.yLabel;
              }

              return label;
            }
          }
        },
        legend: {
          onClick: function(e, legendItem) {
            var index = legendItem.datasetIndex;
            var ci = this.chart;
            var meta = ci.getDatasetMeta(index);

            meta.hidden = meta.hidden === null? !ci.data.datasets[index].hidden : null;
            if (index > 1) {
              ci.config.options.annotation.annotations[index-2].scaleID = meta.hidden ? null : 'x-axis-0';
            }

            ci.update();
          }
        }
      }
    });
    $container.click(function(evt) {
        var activePoints = chart.getElementsAtEvent(evt);
        if (activePoints.length) {
          var mousePos = Chart.helpers.getRelativePosition(evt, chart.chart);
          activePoints = $.grep(activePoints, function(activePoint, index) {
            var leftX = activePoint._model.x - 5,
              rightX = activePoint._model.x + 5,
              topY = activePoint._model.y + 5,
              bottomY = activePoint._model.y - 5;
            return mousePos.x >= leftX && mousePos.x <=rightX && mousePos.y >= bottomY && mousePos.y <= topY;
          });
          for (var i in activePoints) {
            var dsIdx = activePoints[i]._datasetIndex;
            if (dsIdx === 0) {
              window.open(totalUrls[activePoints[i]._index]);
            } else if (dsIdx === 1) {
              window.open(burnedUrls[activePoints[i]._index]);
            }
          }
        }
    });
  }
}

function getProjectIds() {
    var regex = new RegExp('[?&]project_ids(=([^&#]*)|&|#|$)');
    var project_ids = [];
    var results = regex.exec(window.location.href);
    if (results && results[2]) {
      project_ids = decodeURIComponent(results[2].replace(/\+/g, ' ')).split(',');
    }
    return project_ids;
}

function getShowOnlyDatasets() {
    var regex = new RegExp('[?&]dataset_ids(=([^&#]*)|&|#|$)');
    var dataset_ids = [];
    var results = regex.exec(window.location.href);
    if (results && results[2]) {
      dataset_ids = decodeURIComponent(results[2].replace(/\+/g, ' ')).split(',');
    }
    return dataset_ids;
}
// Entrypoint ------------------------------------------------------------------
var loader = new DataLoader(getProjectIds(), getShowOnlyDatasets());
loader.onLoad(function() {
  var chartCount = loader.getChartCount();
  for(var i = 0; i < chartCount; ++i) {
    var renderer = new ProjectRenderer(loader.getChartData(i), loader.getDatasetCount(i));
    renderer.render($('#dashboard'));
  }
  $('#footer').append(
    '<div class="container text-center">' +
      '<p class="text-muted credit small" style="margin-top:30px">' + loader.getGeneratedAt() + '</p>' +
    '</div>'
  );
})
loader.load('./data.json');
