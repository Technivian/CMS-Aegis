
// Bolton theme JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Initialize any interactive components
    console.log('Bolton CLM app loaded');
    
    // Add smooth animations
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });
});
