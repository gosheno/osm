<template>
  <div id="app">
    <RoutePlannerPage />
  </div>
</template>

<script setup>
import RoutePlannerPage from './pages/RoutePlannerPage.vue';
</script>

<style>
* {
  box-sizing: border-box;
}

html,
body,
#app {
  width: 100%;
  height: 100%;
  margin: 0;
}

body {
  overflow: hidden;
  font-family: Inter, Arial, sans-serif;
  background: #f4f6fb;
  color: #1f2937;
}
</style>