const fs = require('fs')
const express = require('express')
const app = express()
const ejs = require('ejs')
const path = require('path')

// set the view engine to ejs
app.set('view engine', 'ejs')
app.set('views', path.join(__dirname, '/public'))

app.use(express.static('public'));

app.get('/', function (req, res) {
  res.render('list')
})

app.get('/list', function (req, res) {
  res.redirect('/')
})

app.get('/offers', function (req, res) {
  const lastModifiedDateOffers = fs.statSync('public/data/steamoffers-new.json').mtime.toISOString().slice(0, 10);
  res.render('offers', {last:lastModifiedDateOffers})
})

app.get('/info', function (req, res) {
  res.render('info')
})

let port = 3000;

app.listen(port, function () {
  console.log('GFNList app listening on port 3000!')
})
