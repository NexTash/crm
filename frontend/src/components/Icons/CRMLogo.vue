<template>
  <svg
    width="300"
    height="300"
    viewBox="0 0 300 300"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <!-- Circle background -->
    <circle cx="150" cy="150" r="140" fill="#121212" />

    <!-- Connection lines -->
    <line x1="150" y1="70" x2="80" y2="200" stroke="#D61F26" stroke-width="12" />
    <line x1="150" y1="70" x2="220" y2="200" stroke="#D61F26" stroke-width="12" />
    <line x1="80" y1="200" x2="220" y2="200" stroke="#D61F26" stroke-width="12" />

    <!-- Connection nodes -->
    <circle cx="150" cy="70" r="20" fill="#D61F26" />
    <circle cx="80" cy="200" r="20" fill="#D61F26" />
    <circle cx="220" cy="200" r="20" fill="#D61F26" />
  </svg>
</template>
