<template>
  <!-- One page per address: a work linking to another work mounts it afresh. -->
  <router-view :key="route.fullPath" />
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router';

/** The Works view (spec: works): the list, a work, the persons and a person. */
const route = useRoute();
</script>
